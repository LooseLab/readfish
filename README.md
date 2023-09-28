<p align="center">
  <img src="https://github.com/LooseLab/readfish/raw/dev_staging/examples/images/readfish_logo.jpg">
</p>

If you are anything like us (Matt), reading a README is the last thing you do when running code.
PLEASE DON'T DO THAT FOR READFISH. This will effect changes to your sequencing and -
if you use it incorrectly - cost you money. We have added a [list of GOTCHAs](#common-gotchas)
at the end of this README. We have almost certainly missed some... so - if something goes
wrong, let us know so we can add you to the GOTCHA hall of fame!

> [!NOTE]  
> We also have more detailed documentation for your perusal at https://looselab.github.io/readfish

> [!NOTE]  
> Now also see our cool [FAQ](docs/FAQ.md).

readfish is a Python package that integrates with the
[Read Until API](https://github.com/nanoporetech/read_until_api).

The Read Until API provides a mechanism for an application to connect to a
MinKNOW server to obtain read data in real-time. The data can be analysed in the
way most fit for purpose, and a return call can be made to the server to unblock
the read in progress and so direct sequencing capacity towards reads of interest.


**This implementation of readfish requires Guppy version >= 6.0.0 and MinKNOW version core >= 5.0.0 . It will not work on earlier versions.**


**Currently we only recommend LINUX for running readfish. We have not had
effective performance on other platforms to date.**

The code here has been tested with Guppy in GPU mode using GridION Mk1 and
NVIDIA RTX2080 on live sequencing runs and an NVIDIA GTX1080 using playback
on a simulated run (see below for how to test this).
This code is run at your own risk as it DOES affect sequencing output. You
are **strongly** advised to test your setup prior to running (see below for
example tests).

<!-- begin-short -->

Citation
--------

The paper is available at [nature biotechnology](https://dx.doi.org/10.1038/s41587-020-00746-x)
and [bioRxiv](https://dx.doi.org/10.1101/2020.02.03.926956)

If you use this software please cite: [10.1038/s41587-020-00746-x](https://dx.doi.org/10.1038/s41587-020-00746-x)

> Readfish enables targeted nanopore sequencing of gigabase-sized genomes
> Alexander Payne, Nadine Holmes, Thomas Clarke, Rory Munro, Bisrat Debebe, Matthew Loose
> Nat Biotechnol (2020); doi: https://doi.org/10.1038/s41587-020-00746-x

Other works
-----------
An update preprint is available at [bioRxiv](https://www.biorxiv.org/content/10.1101/2021.12.01.470722v1)

> Barcode aware adaptive sampling for Oxford Nanopore sequencers
> Alexander Payne, Rory Munro, Nadine Holmes, Christopher Moore, Matt Carlile, Matthew Loose
> bioRxiv (2021); doi: https://doi.org/10.1101/2021.12.01.470722
>
Installation
------------

Our preferred installation method is via [conda](https://conda.io).

The environment is specified as:
```yaml
name: readfish
channels:
  - bioconda
  - conda-forge
  - defaults
dependencies:
  - python=3.10
  - pip
  - pip:
    - readfish[all]
```

Saving the snippet above as `readfish_env.yml` and running the following commands will create the environment.

```console
conda env create -f readfish_env.yml
conda activate readfish
```

#### Installing with development dependencies

A conda `yaml` file is available for installing with dev dependencies - [development.yml](https://github.com/LooseLab/readfish/blob/e30f1fa8ac7a37bb39e9d8b49251426fe1674c98/docs/development.yml)

```bash
curl -LO https://raw.githubusercontent.com/LooseLab/readfish/e30f1fa8ac7a37bb39e9d8b49251426fe1674c98/docs/development.yml?token=GHSAT0AAAAAACBZL42IS3QVM4ZGPPW4SHB6ZE67V6Q
conda env create -f development.yml
conda activate readfish_dev
```

| <h2>‼️ Important! </h2> |
|:---------------------------|
|  The listed `ont-pyguppy-client-lib` version will probably not match the version installed on your system. To fix this, Please see this [FAQ question - connection error timed out.](docs/FAQ.md#connection-error-timed_out-timeout-waiting-for-reply-to-request-load_config)      |


[ONT's Guppy GPU](https://community.nanoporetech.com/downloads) should be installed and running as a server.

<details style="margin-top: 10px">
<summary><h3 style="display: inline;" id="py-ve">Alternatively, readfish can be installed into a python virtual-environment</h3></summary>

```console
# Make a virtual environment
python3 -m venv readfish
. ./readfish/bin/activate
pip install --upgrade pip

# Install our readfish Software
pip install readfish[all]

# Install ont_pyguppy_client_lib that matches your guppy server version. E.G.
pip install ont_pyguppy_client_lib==6.3.8
```

</details>

<details style="margin-top: 10px" open>
<summary id="usage"><h3 style="display: inline;">Usage</h3></summary>

```console
usage: readfish [-h] [--version]  ...

positional arguments:
                   Sub-commands
    targets        Run targeted sequencing
    barcode-targets
                   Run targeted sequencing
    unblock-all    Unblock all reads
    validate       readfish TOML Validator

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit

See '<command> --help' to read about a specific sub-command.

```

</details>
<!-- end-short -->

TOML File
---------
For information on the TOML files see [TOML.md](docs/toml.md).
There are several example TOMLS, with comments explaining what each field does, as well as the overall purpose of the TOML file here - https://github.com//LooseLab/readfish_dev/tree/refactor/docs/_static/example_tomls.

<details style="margin-top: 10px; margin-bottom: 10px"><summary id="testing"><h1 style="display: inline">Testing</h1></summary>
<!-- begin-test -->
To test readfish on your configuration we recommend first running a playback experiment to test unblock speed and then selection.

<!-- #### Configuring bulk FAST5 file Playback -->

<details style="margin-top: 10px"><summary id="configuring-bulk-fast5-file"><h3 style="display: inline;">Configuring bulk FAST5 file Playback</h3></summary>
1. Download an open access bulk FAST5 file from
[here](http://s3.amazonaws.com/nanopore-human-wgs/bulkfile/PLSP57501_20170308_FNFAF14035_MN16458_sequencing_run_NOTT_Hum_wh1rs2_60428.fast5).
This file is 21Gb so make sure you have sufficient space.

The following should all happen with a configuration (test) flow cell inserted into the target device.
A simulated device can also be created within MinKNOW, following these instructions

1. Stop `minknow`

    On Linux:
    ```console
    cd /opt/ont/minknow/bin
    sudo systemctl stop minknow
    ```
1. Start MinKNOW with a simulated device

    On Linux
    ```console
    sudo ./mk_manager_svc -c /opt/ont/minknow/conf --simulated-minion-devices=1 &
    ```

You _may_ need to add the host `127.0.0.1` in the MinKNOW UI.

To setup a simulation the sequencing configuration file that MinKNOW uses must be edited.
Steps:
1. [Download an open access bulk FAST5 file][bulk]. This file is 21Gb so make sure you have plenty of space. This file is a record of a sequencing run using R9.4.1 pores, is non-barcoded and the library was produced using DNA extracted from the NA12878 cell line.
1. Copy file to the `user_scripts` folder:

    On Mac if your MinKNOW output directory is the default:

    ```console
    mkdir -p /Library/MinKNOW/data/user_scripts/simulations
    cp /Applications/MinKNOW.app/Contents/Resources/conf/package/sequencing/sequencing_MIN106_DNA.toml /Library/MinKNOW/data/user_scripts/simulations/sequencing_MIN106_DNA_sim.toml
    ```

    On Linux:

    ```console
    sudo mkdir -p /opt/ont/minknow/conf/package/sequencing/simulations
    cp /opt/ont/minknow/conf/package/sequencing/sequencing_MIN106_DNA.toml /opt/ont/minknow/conf/package/sequencing/simulations/sequencing_MIN106_DNA_sim.toml
    ```

1. Edit the copied file to add the following line under the line that reads "`[custom_settings]`":
   ```text
    simulation = "/full/path/to/your_bulk.FAST5"
   ```
   Change the text between the quotes to point to your downloaded bulk FAST5 file.

    [bulk]: https://s3.amazonaws.com/nanopore-human-wgs/bulkfile/PLSP57501_20170308_FNFAF14035_MN16458_sequencing_run_NOTT_Hum_wh1rs2_60428.fast5
    [ONT]: https://nanoporetech.com

1. Optional, If running GUPPY in GPU mode, set the parameter `break_reads_after_seconds = 1.0`
to `break_reads_after_seconds = 0.4`. This results in a smaller read chunk. For R10.4 this is not required but can be tried. For adaptive sampling on PromethION, this should be left at 1 second.
1. In the MinKNOW GUI, right click on a sequencing position and select `Reload Scripts`.
Your version of MinKNOW will now playback the bulkfile rather than live sequencing.
1. Start a sequencing run as you would normally, selecting the corresponding flow
cell type to the edited script (here FLO-MIN106) as the flow cell type.
1. The run should start and immediately begin a mux scan. Let it run for around
five minutes after which your read length histogram should look as below:
    ![alt text](/_static/images/control.png "Control Image")
</details>

<details style="margin-top: 10px">
<summary id="testing-unblock-response"><h3 style="display: inline;">Testing unblock response</h3></summary>

Now we shall test unblocking by running `readfish unblock-all` which will simply eject
every single read on the flow cell.
1. To do this run:
    ```console
    readfish unblock-all --device <YOUR_DEVICE_ID> --experiment-name "Testing readfish Unblock All"
    ```
1. Leave the run for a further 5 minutes and observe the read length histogram.
If unblocks are happening correctly you will see something like the below:
    ![alt text](/_static/images/Unblock.png "Unblock Image")
A closeup of the unblock peak shows reads being unblocked quickly:
    ![alt text](/_static/images/Unblock_closeup.png "Closeup Unblock Image")

If you are happy with the unblock response, move on to testing base-calling.
</details>

<details style="margin-top: 10px">
<summary id="testing-basecalling-and-mapping"><h3 style="display: inline;">Testing base-calling and mapping</h3></summary>

To test selective sequencing you must have access to a
[guppy basecall server](https://community.nanoporetech.com/downloads/guppy/release_notes) (>=6.0.0)
and configure a TOML file.

1. First make a local copy of the example TOML file:
    ```console
    curl -O https://raw.githubusercontent.com/LooseLab/readfish/master/docs/_static/example_tomls/human_chr_selection.toml
    ```
1. Modify the `fn_idx_in` field in the file to be the full path to a [minimap2](https://github.com/lh3/minimap2) index of the human genome.

1. Modify the `targets` fields for each condition to reflect the naming convention used in your index. This is the sequence name only, up to but not including any whitespace.
e.g. `>chr1 human chromosome 1` would become `chr1`. If these names do not match, then target matching will fail.

We can now validate this TOML file to see if it will be loaded correctly.


    ```console
    readfish validate human_chr_selection.toml
    ```

    Errors with the configuration will be written to the terminal along with a text description of the conditions for the experiment as below.

    ```text
     2023-07-19 11:14:31,091 readfish /path/to/readfish validate human_chr_selection.toml
     2023-07-19 11:14:31,091 readfish command='validate'
     2023-07-19 11:14:31,091 readfish log_file=None
     2023-07-19 11:14:31,091 readfish log_format='%(asctime)s %(name)s %(message)s'
     2023-07-19 11:14:31,091 readfish log_level='info'
     2023-07-19 11:14:31,091 readfish no_check_plugins=True
     2023-07-19 11:14:31,091 readfish prom=False
     2023-07-19 11:14:31,091 readfish toml='human_chr_selection.toml'
     2023-07-19 11:14:31,092 readfish.validate eJydVl1r5TYQffevEM7rre+mzUJbyMNSWBpou6FN6UMIRrbHtogsOZKc5P77zowsX3vjsLQhJNbXnDMzZ0a6EHe98gJ/pbj78vtvoramVZ1olQbRWie0egZRSQ+11FqZTkjTCA8a6oCj7EKEFyvq3tnBejuAFy1+itCD6KdBGtGBwWmhDAJ4PIFmHXTKmgLP3hjcidg12uczmx3iRWmNhJ7B8SKYoByy0valBq3JAJOHVzmMeIoMMfvJQcPk3WQMcX5RoUfi4s+fiqviUlSTfmQP0QJtC+DJmSLLsntyE1zpIdCUL7ppHE8PCQp/iUmCkYFoVtrWj9EQrbEBIvcP+jNCrdqTmMgxwbYiGdr5Dla0F707hx5jsEVFKtG6QmeVWfFC10A3yYBsGgfex8nlSPQjrdmWhze3vwiP2BBS5Ci/GxLFJg4NtHLS4YyBMWAnEngD1dSV2na78EaiMmZsFlywopU+PAk7hXEKZA8Ngax79LBRz6qZpEZ1yObMY/LQTpqhGa3jTM6RuBZ5Y2TpOO/l1ccP1ehLgsizxBm3qLH++Xg8hmE8xhwcP+JPnp3Z4yYqhJKgfdE+5aiUQY7jOns0/k9KiQZ2lcK2VkrZx9oqxUELDkzNYcQN8fieTFpTqua1xNGilM/MaVVMYWPR93bC9FVY1d0PP3IPUA2gIk541thAfgZJRW5OmIbannxBXknvJ8zxuj9IFxPf4CItXB7o7/cHAaH+/7KZBcOi1qozAzYLX6ySsSeT6IdPYfEBx9I14vbTZ9o4yJAImTL0nPt9QtNQYX0ypbgLGSEgo6Fw4ZXBYjwlxhOtItRhKVtqf3ias/qd8wc+SCPW8oW4lY6qTy87iLU1+oQmnyaV2t2IUYbQ33z5Q3gsV4i9ekmdDEKDRPFTzhaHrsVVkZ0VgUo//u3B+SO6H7S1Ho6LDvyR0l96RRIphkHt1cgq/qNs82wDRS32PrZ3/7AuFvluqcjVhXG3ifZsR5zshDE0HHI0hfrztVPVWfB0sxVDw2pZzJCKviWvGVncBAaoeEG6SgUn3QnDabrQpwpGUeFFMlcwC6q3ju4WZESExkA5st6r6kxjUKas+8k8es7WIF/TkLn5pTGEuFkN05B28vcSDjTYyIBxjMdRgkgXJYFpA+6XS7+ORbhCvhaXX6OzLC7EXwBvIhjVaR3d6rFMVtkJ0nUQ9utk3QYivfiQIPmmV8OiNTL4K36KF8TRevIY8gDnp8ebhwc5sEXhVHox4Fl0LdT9fJ3F6VkbG8C75Q1SWnPAkzoo/kqTbbvM0qex2JOf+D913G3KZjRZs6DR4SAf0Z0eDGtacu9xUANWDVGXM8sULacCOCUTLzsGVjvlLvfBjmU8i8zyg8gnwyWDnxSInBMPTV7spnB++LyXRFnho6tcqYFMVoAPr3Klmh2B7viaYr5U7Xx6cZyKn/AEEmIM2s/vQbyfe4sQhfjU0eXioydE8ttyzLiOsSnhO7SkKsyzreKzrdqzpNxrcZ/TjfQhP/D/y/whWzRBBr+KfZZUsrd21g2tphxli4Q2s1FNNJWyl83CWk+9Sc7axJskrU9m/wKwWCn4
     2023-07-19 11:14:31,096 readfish.validate Loaded TOML config without error
     2023-07-19 11:14:31,096 readfish.validate Initialising Caller
     2023-07-19 11:14:31,484 readfish.validate Caller initialised
     2023-07-19 11:14:31,484 readfish.validate Initialising Aligner
     2023-07-19 11:14:38,422 readfish.validate Aligner initialised
    ```
1. If your toml file validates then run the following command:
    ```console
    readfish targets --toml <PATH_TO_TOML> --device <YOUR_DEVICE_ID> --log-file test.log --experiment-name human_select_test
    ```
1. In the terminal window you should see messages reporting the speed of mapping of the form:
    ```text
    2023-06-27 14:10:09,405 readfish.targets 341R/0.31656s
    2023-06-27 14:10:09,838 readfish.targets 283R/0.34924s
    2023-06-27 14:10:10,251 readfish.targets 397R/0.36161s
    2023-06-27 14:10:10,633 readfish.targets 261R/0.34265s
    2023-06-27 14:10:11,048 readfish.targets 394R/0.35735s
    ```

    | :warning: WARNING          |
    |:---------------------------|
    |**Note: if these times are longer than the number of seconds specified in the break read chunk in the sequencing TOML, you will have performance issues. Contact us via github issues for support.**      |

</details>

<details style="margin-top: 10px">
<summary id="testing-expected-results-from-a-selection-experiment"><h3 style="display: inline;">Testing expected results from a selection experiment.</h3></summary>

 The only way to test readfish on a playback run is to look at changes in read length for rejected vs accepted reads. To do this:

 1. Start a fresh simulation run using the bulkfile provided above.
 1. Restart the readfish command (as above):
    ```console
    readfish targets --toml <PATH_TO_TOML> --device <YOUR_DEVICE_ID> --log-file test.log --experiment-name human_select_test
    ```
 1. Allow the run to proceed for at least 15 minutes (making sure you are writing out read data!).
 1. After 15 minutes it should look something like this:
        ![alt text](/_static/images/PlaybackRunUnblock.png "Playback Unblock Image")
Zoomed in on the unblocks:
        ![alt text](/_static/images/PlaybackRunUnblockCloseUp.png "Closeup Playback Unblock Image")


 </details>
 <!-- /Testing expected results from a selection experiment. -->
 </details>
<!-- /Tetsing -->
<!-- end-test -->

<hr size="2px"/>

Common Gotcha's
----
These may or may not (!) be mistakes we have made already...
1. If the previous run has not fully completed - i.e is still basecalling or processing raw data,you may connect to the wrong instance and see nothing happening. Always check the previous run has finished completely.
1. If you have forgotten to remove your simultation line from your sequencing toml you will forever be trapped in an inception like resequencing of old data... Don't do this!
1. If basecalling doesn't seem to be working check:
   - Check your basecalling server is running.
   - Check the ip of your server is correct.
   - Check the port of your server is correct.
1. If you are expecting reads to unblock but they do not - check that you have set `control=false` in your readfish toml file.  `control=true` will prevent any unblocks but does otherwise run the full analysis pipeline.
1. Oh no - every single read is being unblocked - I have nothing on target!
   - Double check your reference file is in the correct location.
   - Double check your targets exist in that reference file.
   - Double check your targets are correctly formatted with contig name matching the record names in your reference (Exclude description - i.e the contig name up to the first whitespace).
1. **Where has my reference gone?** If you are using a _live TOML file - e.g running iter_align or iter_cent, the previous reference MMI file is deleted when a new one is added. This obviously saves on disk space use(!) but can lead to unfortunate side effects - i.e you delete your MMI file. These can of course be recreated but user **beware**.

Happy readfish-ing!

<!-- begin-epilog -->

Acknowledgements
----

We're really grateful to lots of people for help and support. Here's a few of them...

From the lab:
Teri Evans, Sam Holt, Lewis Gallagher, Chris Alder, Thomas Clarke

From ONT:
Stu Reid, Chris Wright, Rosemary Dokos, Chris Seymour, Clive Brown, George Pimm, Jon Pugh

From the Nanopore World:
Nick Loman, Josh Quick, John Tyson, Jared Simpson, Ewan Birney, Alexander Senf, Nick Goldman, Miten Jain, Lukas Weilguny

And for our Awesome Logo please checkout out [@tim_bassford](https://twitter.com/tim_bassford) from [@TurbineCreative](https://twitter.com/TurbineCreative)!

<!-- end-epilog -->
