<!-- PROJECT INTRO -->

OrpheusDL - nugs
=================

A nugs module for the OrpheusDL modular archival music program

[Report Bug](https://github.com/Dniel97/orpheusdl-nugs/issues)
·
[Request Feature](https://github.com/Dniel97/orpheusdl-nugs/issues)


## Table of content

- [About OrpheusDL - nugs](#about-orpheusdl---nugs)
- [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
    - [Global](#global)
    - [nugs](#nugs)
- [Contact](#contact)



<!-- ABOUT ORPHEUS -->
## About OrpheusDL - nugs

OrpheusDL - nugs is a module written in Python which allows archiving from **[nugs.net](https://nugs.net)** for the modular music archival program.


<!-- GETTING STARTED -->
## Getting Started

Follow these steps to get a local copy of Orpheus up and running:

### Prerequisites

* Already have [OrpheusDL](https://github.com/yarrm80s/orpheusdl) installed

### Installation

1. Go to your `orpheusdl/` directory and run the following command:
   ```sh
   git clone --recurse-submodules https://github.com/Dniel97/orpheusdl-nugs.git modules/nugs
   ```
2. Execute:
   ```sh
   python orpheus.py
   ```
3. Now the `config/settings.json` file should be updated with the [nugs settings](#nugs)

<!-- USAGE EXAMPLES -->
## Usage

Just call `orpheus.py` with any link you want to archive:

```sh
python orpheus.py https://play.nugs.net/#/catalog/recording/28751
```

<!-- CONFIGURATION -->
## Configuration

You can customize every module from Orpheus individually and also set general/global settings which are active in every
loaded module. You'll find the configuration file here: `config/settings.json`

### Global

```json5
"global": {
    "general": {
        // ...
        "download_quality": "hifi"
    },
    "codecs": {
        "proprietary_codecs": false,
        "spatial_codecs": true
    },
    // ...
}
```

`download_quality`: Choose one of the following settings:
* "hifi": FLAC with MQA up to 48/24
* "lossless": FLAC or ALAC with 44.1/16
* "high": same as "medium"
* "medium": same as "low"
* "low": same as "minimum"
* "minimum": AAC 150 kbit/s


| Option             | Info                                                                                   |
|--------------------|----------------------------------------------------------------------------------------|
| proprietary_codecs | Enables/Disables MQA downloading regardless the "hifi" setting from `download_quality` |
| spatial_codecs     | Enables/Disables downloading of Sony 360RA                                             |

### nugs
```json
{
    "username": "",
    "password": "",
    "client_id": "Eg7HuH873H65r5rt325UytR5429",
    "dev_key": "x7f54tgbdyc64y656thy47er4"
}
```

| Option    | Info                                                   |
|-----------|--------------------------------------------------------|
| username  | Enter your nugs email address                          |
| password  | Enter your nugs password                               |
| client_id | Enter a valid android client_id from api.aspx          |
| dev_key   | Enter a valid android developerKey from secureApi.aspx |

**Credits: [MQA_identifier](https://github.com/purpl3F0x/MQA_identifier) by
[@purpl3F0x](https://github.com/purpl3F0x) and [mqaid](https://github.com/redsudo/mqaid) by
[@redsudo](https://github.com/redsudo).**

<!-- Contact -->
## Contact

Yarrm80s (pronounced 'Yeargh mateys!') - [@yarrm80s](https://github.com/yarrm80s)

Dniel97 - [@Dniel97](https://github.com/Dniel97)

Project Link: [OrpheusDL nugs Public GitHub Repository](https://github.com/Dniel97/orpheusdl-nugs)
