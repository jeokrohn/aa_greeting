# Update greeting settings for Webex Calling Auto Attendants

This script can be used to update business hours of after hours greeting settings for a set of given auto attendants.
    
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

## Authorization

The script uses an undocumented endpoint to upload auto attendant greetings. This endpoint requires an access token 
with a scope that cannot be included in the list of scopes of a public integration. Hence running this script 
requires the user to provide a Webex developer token which can be obtained from https://developer.webex.com.

Steps to get a developer token:

1) Navigate to https://developer.webex.com
2) Log in using the "Log In" option in the top right
3) Select "Documentation"
4) Scoll down in the list on the left and select "Getting Started" under "APIs"
5) Copy the access token by selecting the copy icon under "Your Personal Access Token"

The developer token can be:

* passed as `--token` argument when calling the script
* set in the environment variable `WEBEX_TOKEN`
* or set in a `.env` file that is loaded by script. See  `.env (sample)` for details.

Developer tokens have a lifetime of 12 hours. After that a new developer token has to be obtained using above steps.

## Using the script with Python installed

If Python (script built and tested with Python 3.10) is installed the requirements for the script can be installed 
via: 

    pip install -r requirements.txt

Then the script can be called using the above syntax. When executed the script generates a log `aa_greeting.log` 
in the current directory which allows to analyze all API calls executed by the script.

This example will reset the business hours greetings of all auto attendants to the default greeting:

    ./aa_greeting.py business default ".*"

The access token in this case is not passed as an argument and thus has to be available either in the `WEBEX_TOKEN` 
environment variable or in a `.env` file in the current directory.

## Using Docker 

If Python is not installed then as an alternative also a Docker image can be built and the script can be run from 
within the Docker container.

To build the Docker image execute: 

    docker build -t aa_greeting .

Then the script can be executed using: 

    docker run --rm aa_greeting --help

The Docker image does not contain a `.env` file. Hence the token has to be passed using the `--token` parameter or 
the token can be put in a local `.env` file and the local directory then is mapped to the `/home` directory using 
the `-v` parameter of `docker run`. See https://docs.docker.com/engine/reference/commandline/run/#volume for 
documentation.

Here's an example of how to map the current directory (referenced by `$PWD`) into the container's `/home` directory: 
    
    docker run --rm -v $PWD:/home aa_greeting business default ".*"

Mapping the local directory into the Docker container also provides direct access to the log file created by the 
script 
running in the container. Without mapping a local directory into the container the log file is created in the 
filesystem within the container.

If you want to upload a greeting file then the file has to be accessible from within the container. The easiest way 
to achieve this is to have the greeting available in the current directory on the host, map the current directory 
into the container, and then reference the greeting without a path:

    docker run --rm -v $PWD:/home aa_greeting business sample.wav ".*"

The shell script `aa_greeting.sh` simplifies usage of the docker image. The script reads am existing `.env` file, 
passes the token defined in either the `.env` file or set in `WEBEX_TOKEN`, maps the current directory into `/home` 
in the container and passes all parameters provided to the script.

This is an example of how to use the script to upload a greeting from the current directory and set that on all auto 
attendants as the business hour greeting:

    ./aa_greeting.sh business sample.wav ".*"
