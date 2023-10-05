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

<details style="margin-top: 10px; margin-bottom: 10px" open><summary id="testing"><h1 style="display: inline">Testing</h1></summary>
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
2023-10-05 15:29:18,934 readfish /home/adoni5/mambaforge/envs/readfish_dev/bin/readfish validate human_chr_selection.toml
2023-10-05 15:29:18,934 readfish command='validate'
2023-10-05 15:29:18,934 readfish log_file=None
2023-10-05 15:29:18,934 readfish log_format='%(asctime)s %(name)s %(message)s'
2023-10-05 15:29:18,934 readfish log_level='info'
2023-10-05 15:29:18,934 readfish no_check_plugins=False
2023-10-05 15:29:18,934 readfish no_describe=False
2023-10-05 15:29:18,934 readfish prom=False
2023-10-05 15:29:18,934 readfish toml='human_chr_selection.toml'
2023-10-05 15:29:18,934 readfish.validate eJydVk1v2zgQvetXEMqlxdryxyZAGyAHt0WKAk1TNNlTkBVoiZKIUKQiUonTX79vSEmW2zRo1/BBIkdvZt68GfKIXXV1zdunU3Z9efGZZUYXsmSFVIIVpmWt4GruZC3YlluRcaWkLmdM6FZmFR7JKDpi7tGwrGpNbayphWWv8MLWS8Z1ztar16zAFnOVYFVXc81KoWHGpGacWaDAWStKaXQCrOtK2v6V8aZREnjOMLiGC661UJbxrDXWesTHylCsyjxmTCiVRAOE2PG6wRYeQ1ZdK/KQVKc1xf4oXYUQ2be3yXGyYttO3e0zd8I6GHm8jxSvzJjjbSkc3LeC2UZkspCAzGUrMqeeKB+KyJlaBZx+AXA1UBiLEYiTZYwXeOD2dLo6s4B3M6FzPLVgjswokj6RGQyrdj1bzlbL5eyvOCYMvxQTbZ8KqsCa0h1Dm3n3AugIOHhB0iBy61+tzAVxwvvEZgyUbw1ICQHYUA5hBWu4c6LVoBJ84eta7gjeG0/TRki+qklmHzwHnr8NXJrCW20FKoUdofLAo9g1ikuNMPBhbbCSC8elGmBzk3U1UuCOBDEHWuVcY08XC2WMFYpvkxJ17LaJNAvINS+krRYUTFK5WpH7d710RTsqwaNFN2E1tcJRrW1Sdk3zdOurMv39639szuJgEY8UW2Y6oFaIRI8tIqglPpKhX5r3bXPoPChE81pEfdOdsTjXPG1XS5JjKt4k6/R4udw2Nj25q76nBbeONLHJ81ZA/T2j5eioz3FONQOLBe+UY7y3JiUFUyhENhkIXLi6WYSMFif4JdFgjFCeNyH/54jjHnm7pnMeVupcPsi844rmBWQTGhD/y6/Xny6/bD4jJu7bFVKivAcdZTQG7jvpBFMkQRLcN1GbB7xDE9T3ubR8SzrKxbYrU2U8UUo+iDQ4K+7joDFZamT//rDCNUbItML0/nKFvcW0wn6BlO0f5q3tc8FI8i4H56RSEFCgp3TmY++sSNhVZTqVU9MI6BQRnm+urjd+AGh2cfEpKnQq810KvSOxRQVKFjw3Wp4sPvTat4t30khNcwRpZRY6L+yiKv9+k2qTcuXAAk/K74nFuHRhA8MgvUjqWlLJLhtiA/X5ujmfVo5oDGl4N39G/+S7hhfk5ktXb5GgF6YvziAPsSP9vwpM0qEwUPl6fNsbEMNGq6fXkU4HnDN2HPng/LFwUGMUzQrxZ1PhiIOMJyvtPBw0IVA/fUaaw2n0QRRSS+dtkFfc6a0y2V2Mady0JhMij30KsXWmgSIzgVaA0GI/3DgBK0w8G0UksyPWf3RKMxGD0IBl7zarOn1HhNNo5o2jwwrzVRS06donoge7Nb8DqjZeSDkUahHZjMlEDMg+E20eB4d9wKfsn/DglUuMDAaHgQ+BDVZ9SFbcd6RqxETZ0jds/AZneEni8jn0NXc/HuX+3An3huFmkdux8s7fH/obAz2tkujmpi/O7W1Ec5KEh/tDSidzHNVSp73DM7ZCHliQdVczPYqw3+5J5CNf4yHGcxHVfLfHOSYcvnseJzQ0nUsjEMpB0WO6FTgeQRryxbghBYUJsUUvpRMXPPNjabhInLGb+Mv7dLlav10vk1V8SwX58bbhbyN7JqNwY0qNnxeH1Yvp+433QeE6Uov0x0TrL0Jebj3lZOI9JFGNg0L+CvBlRC9eh3vZFHvWX60cUwKHhd8afA3RFwV5G9ppmMO/HT3pRDq/CqQAPuTxPPQL2NSq/lu6L/YeLJIIm9AtGez9JBGmLjqCvIxDYPJ7MQltxmaazhqChOdnA/8NyIGWKeJP4jvA/gXiz7IPWqD7mQ16ZnvIyF/n0oNenFDyv3yEG+IeMvoPUvBL7w==
2023-10-05 15:29:18,937 readfish.validate Loaded TOML config without error
2023-10-05 15:29:18,937 readfish.validate Initialising Caller
2023-10-05 15:29:18,945 readfish.validate Caller initialised
2023-10-05 15:29:18,945 readfish.validate Initialising Aligner
2023-10-05 15:29:18,947 readfish.validate Aligner initialised
2023-10-05 15:29:18,948 readfish.validate Configuration description:
Region hum_test (control=False).
Region applies to section of flow cell (# = applied, . = not applied):

    ################################
    ################################
    ################################
    ################################
    ################################
    ################################
    ################################
    ################################

2023-10-05 15:29:18,948 readfish.validate Using the mappy plugin. Using reference: /home/adoni5/Documents/Bioinformatics/refs/hg38_no_alts.fa.gz.split/hg38_chr_M.mmi.

Region hum_test has targets on 1 contig, with 1 found in the provided reference.
This region has 2 total targets (+ve and -ve strands), covering approximately 100.00% of the genome.
```
1. If your toml file validates then run the following command:

1. 
    ```console
    readfish targets --toml <PATH_TO_TOML> --device <YOUR_DEVICE_ID> --log-file test.log --experiment-name human_select_test
    ```

1. In the terminal window you should see messages reporting the speed of mapping of the form:
    ```text
    2023-10-05 15:24:03,910 readfish.targets MinKNOW is reporting PHASE_MUX_SCAN, waiting for PHASE_SEQUENCING to begin.
    2023-10-05 15:25:48,150 readfish._read_until_client Protocol phase changed to PHASE_SEQUENCING
    2023-10-05 15:25:48,724 readfish.targets 0494R/0.5713s; Avg: 0494R/0.5713s; Seq:0; Unb:494; Pro:0; Slow batches (>1.00s): 0/1
    2023-10-05 15:25:52,132 readfish.targets 0004R/0.1831s; Avg: 0249R/0.3772s; Seq:0; Unb:498; Pro:0; Slow batches (>1.00s): 0/2
    2023-10-05 15:25:52,600 readfish.targets 0122R/0.2494s; Avg: 0206R/0.3346s; Seq:0; Unb:620; Pro:0; Slow batches (>1.00s): 0/3
    2023-10-05 15:25:52,967 readfish.targets 0072R/0.2144s; Avg: 0173R/0.3046s; Seq:0; Unb:692; Pro:0; Slow batches (>1.00s): 0/4
    2023-10-05 15:25:53,349 readfish.targets 0043R/0.1932s; Avg: 0147R/0.2823s; Seq:0; Unb:735; Pro:0; Slow batches (>1.00s): 0/5
    2023-10-05 15:25:53,759 readfish.targets 0048R/0.2011s; Avg: 0130R/0.2688s; Seq:0; Unb:783; Pro:0; Slow batches (>1.00s): 0/6
    2023-10-05 15:25:54,206 readfish.targets 0126R/0.2458s; Avg: 0129R/0.2655s; Seq:0; Unb:909; Pro:0; Slow batches (>1.00s): 0/7
    2023-10-05 15:25:54,580 readfish.targets 0082R/0.2180s; Avg: 0123R/0.2595s; Seq:0; Unb:991; Pro:0; Slow batches (>1.00s): 0/8
    2023-10-05 15:25:54,975 readfish.targets 0053R/0.2110s; Avg: 0116R/0.2542s; Seq:0; Unb:1,044; Pro:0; Slow batches (>1.00s): 0/9
    2023-10-05 15:25:55,372 readfish.targets 0057R/0.2051s; Avg: 0110R/0.2492s; Seq:0; Unb:1,101; Pro:0; Slow batches (>1.00s): 0/10
    2023-10-05 15:25:55,817 readfish.targets 0135R/0.2467s; Avg: 0112R/0.2490s; Seq:0; Unb:1,236; Pro:0; Slow batches (>1.00s): 0/11
    2023-10-05 15:25:56,192 readfish.targets 0086R/0.2206s; Avg: 0110R/0.2466s; Seq:0; Unb:1,322; Pro:0; Slow batches (>1.00s): 0/12
    2023-10-05 15:25:56,588 readfish.targets 0060R/0.2138s; Avg: 0106R/0.2441s; Seq:0; Unb:1,382; Pro:0; Slow batches (>1.00s): 0/13
    2023-10-05 15:25:56,989 readfish.targets 0060R/0.2123s; Avg: 0103R/0.2418s; Seq:0; Unb:1,442; Pro:0; Slow batches (>1.00s): 0/14
    2023-10-05 15:25:57,429 readfish.targets 0133R/0.2502s; Avg: 0105R/0.2424s; Seq:0; Unb:1,575; Pro:0; Slow batches (>1.00s): 0/15
    2023-10-05 15:25:57,809 readfish.targets 0089R/0.2280s; Avg: 0104R/0.2415s; Seq:0; Unb:1,664; Pro:0; Slow batches (>1.00s): 0/16
    2023-10-05 15:25:58,210 readfish.targets 0059R/0.2247s; Avg: 0101R/0.2405s; Seq:0; Unb:1,723; Pro:0; Slow batches (>1.00s): 0/17
    ^C2023-10-05 15:25:58,238 readfish.targets Keyboard interrupt received, stopping readfish
    ```

| WARNING                    |
|:---------------------------|
|**Note: if these times are longer than the number of seconds specified in the break read chunk in the sequencing TOML, you will have performance issues. Contact us via github issues for support.**      |
<!-- start-heartbeat-log -->
This log is a little dense at first. Moving from left to right, we have:

    [Date Time] [Logger Name] [Batch Stats]; [Average Batch Stats]; [Count commands sent]; [Slow Batch Info]

Using the provided log as an example:

On 2023-10-05 at 15:25:56,989, the Readfish targets command logged a batch of read signal:

    - It saw 60 reads in the current batch.
    - The batch took 0.2123 seconds.
    - On average, batches are 103 reads, which are processed in 0.2418 seconds.
    - Since the start, 0 reads were sequenced, 1,442 reads were unblocked, and 0 reads were asked to proceed.
    - Out of 14 total batches processed, 0 were considered slow (took more than 1 second).

The important thing to note here is that the average batch time is less than the break read chunk time in the sequencing TOML.
The slow batch section will show the number of batches that were slower than break reads. 
If the average is lower, or the slow batch count is high,  you will have performance issues.
Contact us via github issues for support.
<!-- end-heartbeat-log -->
If you are happy with the speed of mapping, move on to testing a selection.

</details>

<details style="margin-top: 10px">
<summary id="testing-expected-results-from-a-selection-experiment"><h3 style="display: inline;">Testing expected results from a selection experiment.</h3></summary>

 The only way to test readfish on a playback run is to look at changes in read length for rejected vs accepted reads. To do this:

 1. Start a fresh simulation run using the bulkfile provided above.
 2. Restart the readfish command (as above):
    ```console
    readfish targets --toml <PATH_TO_TOML> --device <YOUR_DEVICE_ID> --log-file test.log --experiment-name human_select_test
    ```
 3. Allow the run to proceed for at least 15 minutes (making sure you are writing out read data!).
 4. After 15 minutes it should look something like this:
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
