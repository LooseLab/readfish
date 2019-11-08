Read Until
==========

This is a Python3 implementation of the [Read Until API](https://github.com/nanoporetech/read_until_api).

---

The Read Until API provides a mechanism for an application to connect to a
MinKNOW server to obtain read data in real-time. The data can be analysed in the
way most fit for purpose, and a return call can be made to the server to unblock
the read in progress.

Developers are directed to the
[Developer Channel](https://community.nanoporetech.com/posts/channels/developers)
of the Nanopore Community for support (Issue reporting has been disabled on the
github website).

![Read Until Example](https://github.com/nanoporetech/read_until_api/raw/dev/read_until.gif)

Installation
------------

```bash
$ git clone https://github.com/looselab/ru3.git
$ git clone https://github.com/looselab/pyguppyplay.git
$ cd ru3
$ python3 -m venv venv3
$ source ./venv3/bin/activate
$ pip install --upgrade pip -r requirements.txt
$ python setup.py develop
$ cd ../pyguppyplay
$ pip install -r requirements.txt
$ python setup.py develop
```

You can now use `pip list` to check that pyguppy and read_until are both installed with the correct directories.

<details>
<summary>Python2 installation</summary>
    The client requires MinKNOW for MinION 18.02 or later (MinKNOW-Core 1.12).
    
    The package can be installed into MinKNOW's python environment using the python
    interpreter in the MinKNOW root directory. For example on Ubuntu:
    
        sudo /opt/ONT/MinKNOW/ont-python/bin/python setup.py install
    
    (The MinKNOW python is located at
    `/Applications/MinKNOW.app/Contents/Resources/ont-python/bin/python` on OSX
    and `C:\Program Files\OxfordNanopore\MinKNOW\ont-python\python.exe` on Windows).
    
    Installation of the package into other python environments is currently
    unsupported. An example installation process for Ubuntu including installing
    additional python modules can be found in [Ubuntu Install](./INSTALL.md).
    
    Two demonstration programs are provided (and are installed into
    MinKNOW/ont-python/bin/):
    
       1.  `read_until_simple`: this serves as a simple test, and the code
           (module `read_until.simple`) demonstrates use of basic functionality
           for developers.
       2.  `read_until_ident`: this is a rather more fully featured example, using
           the API to identify reads via basecalling and alignment. To run it
           requires the optional dependencies of scrappy and mappy. These can be
           installed via `ont-python/bin/python -m pip install mappy scrappie`.
           To use the `scrappy` basecaller efficiently it is important to set
           the blas library to be single threaded, this is ordinarily done with:
    
               export OPENBLAS_NUM_THREADS=1
    
           or similar.
</details>

Client Overview
---------------

The python Read Until package provides a high level interface to requisite parts
of MinKNOW's [gRPC](https://grpc.io/) interface. Developer's can focus on
creating rich analyses, rather than the lower level details of handling the data
that MinKNOW provides. The purpose of the read until functionality is to
selectively, based on any conceiveable analysis, "unblock" sequencing channels
to increases the time spent sequencing analytes of interest. MinKNOW can be
requested to send a continuous stream of "read chunks" (of a configurable
minimum size), which the client can analyse.

The main client code is located in the `read_until.base.ReadUntilClient` class,
which can be imported as simply:

    from read_until import ReadUntilClient

The interface to this class is thoroughly documented, with additional comments
throughout for developers who wish to develop their own custom client from the
gRPC stream. Developers are encouraged to read the code and inline documentation
(a HTML version of which can be built using the `docs` make target). 

The gRPC stream managed by the client is bidirectional: it carries both raw data
"read chunks" to the client and "action responses" to MinKNOW. The client
implements two queues. The first is the `.action_queue` and is fairly
straight-forward: requests to MinKNOW to unblock channels are temporarily stored
here, bundled together and then dispatched.

The second queue is more elaborate, it is implemented in
`read_until.base.ReadCache`. The client stores read chunks here in preparation
for analysis. The queue is additionally keyed on channel such that it only ever
stores a single chunk from each sequencer channel; thereby protecting consumers
of the client from reads which have already ended. A restriction of this
approach is that consumers cannot combine data from multiple chunks of the same
read. If this behaviour is required, a client can be constructed with an
alternative implementation of a `ReadCache` (passed as a parameter on
construction of the `ReadUntilClient` instance). However since the effectiveness
of a read until application depends crucially on the latency of analysis, it is
recommended to design analyses which require as little data as possible and set
the received chunk size accordingly.

For many developers the details of these queues may be unimportant, at least in
getting started. Of more immediate importance are several methods of the
`ReadUntilClient` class:

*`.run()`*
instruct the class to start retrieving read chunks from MinKNOW.

*`.get_read_chunks()`*
obtain the most recent data retrieved from MinKNOW.

*`.unblock_read()`*
request that a read be ejected from a channel.

*`.stop_recieving_read()`*
request that no more data for a read be sent to the client by MinKNOW. It is not
guaranteed that further data will not be sent, and in the general case the
client does not filter subsequent data from its consumers (although when the
client is created with the `one_chunk` option, the client will provide
additional filtering of the data received from MinKNOW).

Examples of use of the client are given in the codebase, but most simply can be
reduced to:

    from concurrent.futures import ThreadPoolExecutor
    import numpy
    from read_until import ReadUntilClient

    def analysis(client, *args, **kwargs):
        while client.is_running:
            for channel, read in client.get_read_chunks():
                raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
                # do something with raw data... and maybe call:
                #    client.stop_receiving_read(channel, read.number)
                #    client.unblock_read(channel, read.number)
    
    read_until_client = ReadUntilClient()
    read_until_client.run()
    with ThreadPoolExecutor() as executor:
        executor.submit(analysis, read_until_client)


Extending the client
--------------------

The `ReadUntilClient` class has been implemented to provide an abstraction which
does not require an in-depth knowledge of the MinKNOW gRPC interface. To extend
the client however some knowledge of the messages passed between MinKNOW and a
client is required. Whilst the provided client shows how to contruct and decode
basic messages, the following (an extract from Protocol Buffers definition
files) serves as a more complete reference.

**Messages sent from a client to MinKNOW**

    message GetLiveReadsRequest {
        enum RawDataType {
            // Don't change the previously specified setting for raw data sent
            // with live reads note: If sent when there is no last setting, NONE
            // is assumed.
            KEEP_LAST = 0;
            // No raw data required for live reads
            NONE = 1;
            // Calibrated raw data should be sent to the user with each read
            CALIBRATED = 2;
            // Uncalibrated data should be sent to the user with each read
            UNCALIBRATED = 3;
        }
    
        message UnblockAction {
            // Duration of unblock in seconds.
            double duration = 1;
        }
    
        message StopFurtherData {}
    
        message Action {
            string action_id = 1;

            // Channel name to unblock
            uint32 channel = 2;
    
            // Identifier for the read to act on. If the read requested is no
            // longer in progress, the action fails.
            oneof read { string id = 3; uint32 number = 4; }
    
            oneof action {
                // Unblock a read and skip further data from this read.
                UnblockAction unblock = 5;
    
                // Skip further data from this read, doesn't affect the read
                // data.
                StopFurtherData stop_further_data = 6;
            }
        }
    
        message StreamSetup {
            // The first channel (inclusive) for which to return data. Note
            // that channel numbering starts at 1.
            uint32 first_channel = 1;
    
            // The last channel (inclusive) for which to return data.
            uint32 last_channel = 2;
    
            // Specify the type of raw data to retrieve
            RawDataType raw_data_type = 3;
    
            // Minimum chunk size read data is returned in.
            uint64 sample_minimum_chunk_size = 4;
        }
    
        message Actions { repeated Action actions = 2; }
    
        oneof request {
            // Read setup request, initialises channel numbers and type of data
            // returned. Must be specified in the first message sent to MinKNOW.
            // Once MinKNOW has the first setup message reads are sent to the
            // caller as requested. The user can then resend a setup message as
            // frequently as they need to in order to reconfigure live reads -
            // for example by changing if raw data is sent with reads or not.
            StreamSetup setup = 1;
    
            // Actions to take given data returned to the user - can only be
            // sent once the setup message above has been sent.
            Actions actions = 2;
        }
    }


**Messages received by a client from MinKNOW**

    message GetLiveReadsResponse {
        message ReadData {
            // The id of this read, this id is unique for every read ever
            // produced.
            string id = 1;
    
            // The MinKNOW assigned number of this read. Read numbers always
            // increment throughout the experiment, and are unique per channel,
            // however they are not necessarily contiguous.
            uint32 number = 2;
            
            // Absolute start point of this read
            uint64 start_sample = 3;
            
            // Absolute start point through the experiment of this chunk
            uint64 chunk_start_sample = 4;
            
            // Length of the chunk in samples
            uint64 chunk_length = 5;
            
            // All Classifications given to intermediate chunks by analysis
            repeated int32 chunk_classifications = 6;
            
            // Any raw data selected by the request. The type of the elements
            // will depend on whether calibrated data was chosen. The
            // get_data_types() RPC call should be used to determine the
            // precise format of the data, but in general terms, uncalibrated
            // data will be signed integers and calibrated data will be
            // floating-point numbers.
            bytes raw_data = 7;
            
            // The median of the read previous to this read. intended to allow
            // querying of the approximate level of this read, comapred to the
            // last. For example, a user could try to verify this is a strand be
            // ensuring the median of the current read is lower than the
            // median_before level.
            float median_before = 8;
            
            // The media pA level of this read from all aggregated read chunks
            // so far.
            float median = 9;
        };
        
        message ActionResponse {
            string action_id = 1;
            enum Response { SUCCESS = 0; FAILED_READ_FINISHED = 1; }
            Response response = 2;
        }
        
        // The number of samples collected before the first sample included is
        // this response. This gives the position of the first data point on
        // each channel in the overall stream of data being acquired from the
        // device (since this period of data acquisition was started).
        uint64 samples_since_start = 1;
        
        // The number of seconds elapsed since data acquisition started.
        // This is the same as ``samples_since_start``, but expressed in
        // seconds.
        double seconds_since_start = 2;
        
        // In progress reads for the requested channels. Sparsely populated as
        // not all channels have new/incomplete reads.
        map<uint32, ReadData> channels = 4;
        
        // List of responses to requested actions, informing the caller of
        // results to requested unblocks or discards of data.
        repeated ActionResponse action_reponses = 5;
    }
