#!/usr/bin/env python
"""
Update greeting settings for a number of auto attendants

    usage: aa_greeting.py [-h] [--token TOKEN] menu greeting ...

    positional arguments:
      menu           "business" or "after_hours"
      greeting       greeting file or "default"
      aaname         name of AA to modify. An be a tuple with location name and AA name like "location:aa1". Also
                     the AA name can be a regular expression. For example "location:.*" would catch all AAs in given
                     location. Multiple AA name specs can be given.

    optional arguments:
      -h, --help     show this help message and exit
      --token TOKEN  access token. If not provided will be read from "WEBEX_TOKEN environment variable
"""
import argparse
import asyncio
import logging
import os
import re
import sys
from asyncio import Lock
from dataclasses import dataclass, field
from itertools import chain
from os.path import isfile
from typing import Optional

from aiohttp import FormData, ClientSession
from dotenv import load_dotenv

from wxc_sdk.as_api import AsWebexSimpleApi
from wxc_sdk.as_rest import as_dump_response
from wxc_sdk.base import webex_id_to_uuid
from wxc_sdk.common import Greeting, MediaFileType
from wxc_sdk.locations import Location
from wxc_sdk.telephony.autoattendant import AutoAttendant, AutoAttendantAudioFile


def aa_str(aa: AutoAttendant):
    return f'"{aa.location_name}:{aa.name}"'


async def upload_aa_greeting(*, access_token: str, org_id: str, location_id: str, aa_id: str,
                             business: bool,
                             path: str):
    """
    Upload an AA greeting
    :param access_token:
    :param org_id:
    :param location_id:
    :param aa_id:
    :param business: True: business greeting, False: after hours
    :param path: path to WAV file
    :return:
    """

    action = 'businessgreetingupload' if business else 'afterhoursgreetingupload'
    url = f'https://cpapi-r.wbx2.com/api/v1/customers/{webex_id_to_uuid(org_id)}/locations/' \
          f'{webex_id_to_uuid(location_id)}/features/autoattendants/{webex_id_to_uuid(aa_id)}' \
          f'/actions' \
          f'/{action}/invoke?customGreetingEnabled=true'
    async with ClientSession() as session:
        with open(path, mode='rb') as file:
            data = FormData()
            data.add_field('file', file,
                           filename=os.path.basename(path),
                           content_type='audio/wav')
            headers = {'authorization': f'Bearer {access_token}'}
            async with session.post(url=url, data=data, headers=headers) as r:
                as_dump_response(response=r)
                r.raise_for_status()
    return


@dataclass
class AAPicker:
    api: AsWebexSimpleApi = field(repr=False)
    aa_specs: list[str]
    # cached list of locations
    _locations: Optional[list[Location]] = field(init=False, repr=False, default=None)
    # lock to protect getting list of locations from Webex
    _locations_lock: Lock = field(init=False, repr=False, default_factory=Lock)

    async def locations(self) -> list[Location]:
        """
        Get (cached) list of locations. If no cached list exist, then get list of location from Webex
        :return:
        """
        async with self._locations_lock:
            if not self._locations:
                self._locations = await self.api.locations.list()
        return self._locations

    async def pick_one_spec(self, spec: str) -> list[AutoAttendant]:
        """
        Pick AutoAttendant instances based on a single AA spec
        Raises KeyError if the spec is invalid (format issues, no match, ...)
        """
        location_and_aa = spec.split(':')
        if len(location_and_aa) == 1:
            aa_spec = location_and_aa[0]
            location_id = None
        elif len(location_and_aa) == 2:
            location_spec, aa_spec = location_and_aa
            # find location
            location = next((loc for loc in await self.locations()
                             if loc.name == location_spec), None)
            if location is None:
                print(f'Location not found: "{location_spec}"')
                raise KeyError
            location_id = location.location_id
        else:
            print(f'Invalid AA spec: {spec}')
            raise KeyError
        try:
            aa_re = re.compile(f'^{aa_spec}$')
        except re.error as e:
            print(f'invalid AA spec: "{aa_spec}": {e}')
            raise KeyError
        # get all AA instances matching the spec
        aa_list = [aa for aa in await self.api.telephony.auto_attendant.list(location_id=location_id)
                   if aa_re.match(aa.name)]
        return aa_list

    async def pick(self) -> list[AutoAttendant]:
        """
        Get list of AutoAttendant instances based on provided AA specs
        """
        results = await asyncio.gather(*[self.pick_one_spec(spec)
                                         for spec in self.aa_specs],
                                       return_exceptions=True)
        exc = next((r for r in results if isinstance(r, Exception)), None)
        if exc:
            # is there an exception other than a KeyError?
            exc = next((r for r in results if isinstance(r, Exception) and not isinstance(r, KeyError)), None)
            if exc:
                raise exc
            exit(1)
        results: list[list[AutoAttendant]]
        # potentially we had overlapping AA specs; make sure that each AA is only returned once
        aa_ids = set()
        aa_list = []
        for aa in chain.from_iterable(results):
            if aa.auto_attendant_id not in aa_ids:
                aa_list.append(aa)
                aa_ids.add(aa.auto_attendant_id)
        return aa_list


async def update_aa(*, api: AsWebexSimpleApi, org_id: str, aa: AutoAttendant, menu: str, greeting: str):
    """
    Update a single AA
    """

    def info(s: str):
        print(f'{aa_name}: {s}', file=sys.stderr)

    details = await api.telephony.auto_attendant.details(location_id=aa.location_id,
                                                         auto_attendant_id=aa.auto_attendant_id,
                                                         org_id=org_id)
    aa_name = aa_str(aa)
    info('got details')

    update = details.copy(deep=True)
    if menu == 'business':
        update_menu = update.business_hours_menu
    else:
        update_menu = update.after_hours_menu
    if greeting == 'default':
        # set to 'default'
        if update_menu.greeting == Greeting.default:
            info('nothing to do')
            return
        update_menu.greeting = Greeting.default
    else:
        basename = os.path.basename(greeting)
        if update_menu.greeting == Greeting.custom and update_menu.audio_file.name == basename:
            # custom greeting with same file name already set
            info('nothing to do')
            return

        # upload greeting if needed
        if update_menu.audio_file and update_menu.audio_file.name == basename:
            info(f'greeting "{basename}" already uploaded')
        else:
            await upload_aa_greeting(access_token=api.access_token,
                                     org_id=org_id,
                                     location_id=aa.location_id,
                                     aa_id=aa.auto_attendant_id,
                                     business=menu == 'business',
                                     path=greeting)
            info(f'uploaded new greeting "{basename}"')

        # set to uploaded greeting
        update_menu.greeting = Greeting.custom
        update_menu.audio_file = AutoAttendantAudioFile(name=basename,
                                                        media_type=MediaFileType.wav)
    # apply update
    await api.telephony.auto_attendant.update(location_id=aa.location_id,
                                              auto_attendant_id=aa.auto_attendant_id,
                                              settings=update,
                                              org_id=org_id)
    info(f'updated settings')


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', type=str, help='access token. If not provided will be read from "WEBEX_TOKEN '
                                                  'environment variable')
    parser.add_argument('menu', type=str, help='"business" or "after_hours"')
    parser.add_argument('greeting', type=str, help='greeting file or "default"')
    parser.add_argument('aaname', type=str, help='name of AA to modify. An be a tuple with location name and AA name '
                                                 'like "location:aa1". Also the AA name can be a regular expression. '
                                                 'For example "location:.*" would catch all AAs in given location. '
                                                 'Multiple AA name specs can be given.',
                        nargs=argparse.REMAINDER)
    args = parser.parse_args()
    load_dotenv()
    token = args.token or os.getenv('WEBEX_TOKEN')
    if token is None:
        print('Need to provide an access token using --token or set one in the WEBEX_TOKEN environment variable',
              file=sys.stderr)
        exit(1)
    menu = args.menu.lower()
    if menu not in ('business', 'after_hours'):
        print(f'Invalid argument for menu "{menu}". Allowed: business, after_hours', file=sys.stderr)
        exit(1)

    greeting = args.greeting
    if greeting.lower() == 'default':
        greeting = 'default'
    elif not isfile(greeting):
        print(f'File not found: {greeting}', file=sys.stderr)
        exit(1)

    async with AsWebexSimpleApi(tokens=token) as api:
        aa_name = args.aaname
        picker = AAPicker(api=api, aa_specs=args.aaname)
        aa_list = await picker.pick()

        if not aa_list:
            print('No AAs found', file=sys.stderr)
            exit(1)

        aa_list.sort(key=lambda aa: (aa.location_name, aa.name))
        print('Updating:', file=sys.stderr)
        print("\n".join(f'  - {aa_str(aa)}' for aa in aa_list), file=sys.stderr)
        print(file=sys.stderr)

        # update AAs concurrently
        org_id = (await api.people.me()).org_id
        results = await asyncio.gather(*[update_aa(api=api, org_id=org_id, aa=aa, menu=menu, greeting=greeting) for aa
                                         in aa_list],
                                       return_exceptions=True)
        # print results
        print(file=sys.stderr)
        for aa, result in zip(aa_list, results):
            if isinstance(result, Exception):
                r = f'{result}'
            else:
                r = 'ok'
            print(f'{aa.location_name}:{aa.name}: {r}', file=sys.stderr)
    return


if __name__ == '__main__':
    logging.basicConfig(filename=f'{os.path.splitext(os.path.basename(__file__))[0]}.log', filemode='w',
                        level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    asyncio.run(main())
