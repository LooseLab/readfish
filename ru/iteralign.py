"""
Iter-align.
Design spec.
    1. Grab fastq files from a location.
    2. Align the files ONCE to a reference.
    3. Calculate cumulative coverage information.
    4. Write a list of genomes that are covered at a particular threshold.
    5. Rinse and repeat
"""
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
from io import StringIO

import pandas as pd
import toml
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver as Observer

from ru.arguments import get_parser
from ru.utils import nice_join, print_args, send_message, Severity
from read_until_api_v2.load_minknow_rpc import get_rpc_connection, parse_message


DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)-20s - %(message)s"
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
DEFAULT_COVERAGE_DEPTH = 30
DEFAULT_PERCENTAGE_COVERED = 0.99
DEFAULT_CORES = 2


_help = "ReadFish and Run Until, using minimap2"
_cli = (
    (
        "--host",
        dict(
            metavar="HOST",
            help="MinKNOW server host",
            default=DEFAULT_SERVER_HOST,
        ),
    ),
    (
        "--device",
        dict(
            metavar="DEVICE",
            type=str,
            help="Name of the sequencing position e.g. MS29042 or GA10000 etc.",
            required=True,
        ),
    ),
    (
        "--watch",
        dict(
            metavar="FOLDER",
            help="Top Level Folder containing fastq reads.",
            default=None,
        ),
    ),
    (
        "--percent",
        dict(
            metavar="PERCENT",
            help="Default percent of target covered at given depth (default {})".format(DEFAULT_PERCENTAGE_COVERED),
            default=DEFAULT_PERCENTAGE_COVERED,
            type=float,
        ),
    ),
    (
        "--depth",
        dict(
            metavar="DEPTH",
            help="Desired coverage depth (default {})".format(DEFAULT_COVERAGE_DEPTH),
            default=DEFAULT_COVERAGE_DEPTH,
            type=int,
        ),
    ),
    (
        "--threads",
        dict(
            metavar="THREADS",
            help="Set the number of default threads to use for threaded tasks (default {})".format(DEFAULT_CORES),
            default=DEFAULT_CORES,
            type=int,
        ),
    ),
    (
        "--log-level",
        dict(
            metavar="LOG-LEVEL",
            action="store",
            default="info",
            choices=LOG_LEVELS,
            help="One of: {}".format(nice_join(LOG_LEVELS)),
        ),
    ),
    (
        "--log-format",
        dict(
            metavar="LOG-FORMAT",
            action="store",
            default=DEFAULT_LOG_FORMAT,
            help="A standard Python logging format string (default: {!r})".format(
                DEFAULT_LOG_FORMAT.replace("%", "%%")
            ),
        ),
    ),
    (
        "--log-file",
        dict(
            metavar="LOG-FILE",
            action="store",
            default=None,
            help="A filename to write logs to, or None to write to the standard stream (default: None)",
        ),
    ),
    (
        "--toml",
        dict(
            metavar="TOML",
            required=True,
            help="The magic TOML file that will save your life?",
            #type=toml.load,
        ),
    ),
)


def file_dict_of_folder_simple(path, args, logging, fastqdict):
    logger = logging.getLogger("ExistingFileProc")

    file_list_dict = dict()

    counter = 0

    if os.path.isdir(path):

        logger.info("caching existing fastq files in: %s" % (path))

        for path, dirs, files in os.walk(path):

            for f in files:

                counter += 1

                if f.endswith(".fastq") or f.endswith(".fastq.gz"):

                    logger.debug("Processing File {}\r".format(f))
                    filepath = os.path.join(path, f)
                    file_list_dict[filepath] = os.stat(filepath).st_mtime

    logger.info("processed %s files" % (counter))



    logger.info("found %d existing fastq files to process first." % (len(file_list_dict)))

    return file_list_dict


def parse_fastq_file(fastqfilelist,args,logging,masterdf):
    logger = logging.getLogger("ParseFastq")

    with open(os.devnull, 'w') as devnull:
        # Run basic mapping
        minimapcmd = ["minimap2","-ax","map-ont","-t {}".format(args.threads),args.toml['conditions']['reference']] #" ".join(fastqfilelist)]
        minimapcmd.extend(fastqfilelist)
        logger.info(" ".join(minimapcmd))
        minimapoutput = subprocess.Popen(minimapcmd, stdout=subprocess.PIPE,stderr=devnull)
        samcmd = ["samtools","view", "-bS"]
        samoutput = subprocess.Popen(samcmd, stdin=minimapoutput.stdout, stdout=subprocess.PIPE, stderr=devnull)
        #samsortcmd = ["samtools", "sort", "-@2", "-o", "sortedbam.bam"]
        samsortcmd = ["samtools", "sort", "-@{}".format(args.threads)]
        samsortoutput = subprocess.Popen(samsortcmd, stdin=samoutput.stdout, stdout=subprocess.PIPE, stderr=devnull)
        samdepthcmd = ["samtools", "depth", "-a", "/dev/stdin"]
        samdepthoutput = subprocess.Popen(samdepthcmd, stdin=samsortoutput.stdout,stdout=subprocess.PIPE, stderr=devnull, universal_newlines=True)
        minimapoutput.stdout.close()
        samoutput.stdout.close()
        samsortoutput.stdout.close()
        output,err = samdepthoutput.communicate()

        coveragedf = pd.read_csv(StringIO(output),sep="\t",names=['seqid','position','coverage'])


        summarydf = coveragedf.groupby('seqid', as_index=False).agg({'position':'max','coverage':'sum'})


        tempsummarydf = pd.concat([masterdf,summarydf])
        masterdf = tempsummarydf.groupby('seqid', as_index=False).agg({'position': 'max', 'coverage': 'sum'})
        masterdf["tmp"] = masterdf["coverage"]/masterdf['position']
        # Calculate depth at every position
        targets = masterdf[masterdf["tmp"].ge(args.depth)]

        logger.info(targets)

        targets = targets['seqid'].tolist()

        masterdf.drop(['tmp'], axis=1, inplace=True)

        logger.info("Finished processing {}.".format(" ".join(fastqfilelist)))

    return targets,masterdf



def write_new_toml(args,targets):
    for k in args.toml["conditions"].keys():
        curcond = args.toml["conditions"].get(k)
        if isinstance(curcond,dict):

            #newtargets = targets
            #newtargets.extend(curcond["targets"])

            #newtargets = list(dict.fromkeys(newtargets))
            #curcond["targets"]=list(set(newtargets))
            curcond["targets"]=targets

    with open("{}_live".format(args.tomlfile), "w") as f:
        toml.dump(args.toml,f)




class FastqHandler(FileSystemEventHandler):

    def __init__(self, args,logging,messageport,rpc_connection):
        self.args = args
        self.messageport = messageport
        self.connection = rpc_connection
        self.logger = logging.getLogger("FastqHandler")
        self.running = True
        self.fastqdict = dict()
        self.creates = file_dict_of_folder_simple(self.args.watch, self.args, logging,
                                                  self.fastqdict)
        self.t = threading.Thread(target=self.processfiles)

        try:
            self.t.start()
        except KeyboardInterrupt:
            self.t.stop()
            raise


    def processfiles(self):
        self.logger.info("Process Files Inititated")
        self.counter = 0
        self.targets = []
        self.masterdf = pd.DataFrame(columns=['seqid','position','coverage'])

        while self.running:
            currenttime = time.time()
            #for fastqfile, createtime in tqdm(sorted(self.creates.items(), key=lambda x: x[1])):
            fastqfilelist=list()
            for fastqfile, createtime in sorted(self.creates.items(), key=lambda x: x[1]):

                delaytime = 0

                # file created 5 sec ago, so should be complete. For simulations we make the time longer.
                if (int(createtime) + delaytime < time.time()):
                    self.logger.info(fastqfile)
                    del self.creates[fastqfile]
                    self.counter +=1
                    fastqfilelist.append(fastqfile)

                    #print (fastqfile,md5Checksum(fastqfile), "\n\n\n\n")
            targets,self.masterdf = parse_fastq_file(fastqfilelist,self.args,logging,self.masterdf)
            print (targets)
            print (self.targets)
            if len(targets) > len(self.targets):
                updated_targets = set(targets) - set(self.targets)
                update_message = "Updating targets with {}".format(nice_join(updated_targets, conjunction="and"))
                self.logger.info(update_message)
                if not self.args.simulation:
                    send_message(self.connection, update_message, Severity.WARN)
                write_new_toml(self.args,targets)
                self.targets = []
                self.targets = targets.copy()

            if self.masterdf.shape[0] > 0 and self.masterdf.shape[0] == len(self.targets):
                # Every target is covered at the desired coverage level.
                self.logger.info("Every target is covered at at least {}x".format(self.args.depth))
                if not self.args.simulation:
                   self.connection.protocol.stop_protocol()
                   send_message(
                       self.connection,
                       "Iter Align has stopped the run as all targets should be covered by at least {}x".format(
                           self.args.depth
                       ),
                       Severity.WARN,
                   )


            #parse_fastq_file(fastqfile, self.rundict, self.fastqdict, self.args, self.header, self.MinotourConnection)

            #self.args.files_processed += 1

            if currenttime+5 > time.time():
                time.sleep(5)

    def on_created(self, event):
        """Watchdog counts a new file in a folder it is watching as a new file"""
        """This will add a file which is added to the watchfolder to the creates and the info file."""
        # if (event.src_path.endswith(".fastq") or event.src_path.endswith(".fastq.gz")):
        #     self.creates[event.src_path] = time.time()


        # time.sleep(5)
        if (event.src_path.endswith(".fastq") or event.src_path.endswith(".fastq.gz") or event.src_path.endswith(
                ".fq") or event.src_path.endswith(".fq.gz")):
            self.logger.info("Processing file {}".format(event.src_path))
            self.creates[event.src_path] = time.time()

    def on_modified(self, event):
        if (event.src_path.endswith(".fastq") or event.src_path.endswith(".fastq.gz") or event.src_path.endswith(
                ".fq") or event.src_path.endswith(".fq.gz")):
            self.logger.info("Processing file {}".format(event.src_path))
            self.logger.debug("Modified file {}".format(event.src_path))
            self.creates[event.src_path] = time.time()

    def on_moved(self, event):
        if any((event.dest_path.endswith(".fastq"), event.dest_path.endswith(".fastq,gz"),
                event.dest_path.endswith(".gq"), event.dest_path.endswith(".fq.gz"))):
            self.logger.info("Processing file {}".format(event.dest_path))
            self.logger.debug("Modified file {}".format(event.dest_path))
            self.creates[event.dest_path] = time.time()



def main():
    sys.exit(
        "This entry point is deprecated, please use 'readfish align' instead"
    )


def run(parser, args):
    args.tomlfile = args.toml
    args.toml = toml.load(args.toml)
    print (args)

    # TODO: Move logging config to separate configuration file
    # set up logging to file
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s::%(asctime)s::%(name)s::%(message)s',
                        filename=args.log_file,
                        filemode='w')

    # define a Handler that writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    # set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-15s: %(levelname)-8s %(message)s')
    console.setFormatter(formatter)

    # add the handler to the root logger
    logging.getLogger('').addHandler(console)

    # Start by logging sys.argv and the parameters used
    logger = logging.getLogger("Manager")
    logger.info(" ".join(sys.argv))
    print_args(args, logger=logger)

    logger.info("Initialising iterAlign.")

    logger.info("Setting up FastQ monitoring.")



    #### Check if a run is active - if not, wait.

    args.simulation = True
    connection = None
    if args.watch is None:
        args.simulation = False
        logger.info("Creating rpc connection for device {}.".format(args.device))
        try:
            connection, messageport = get_rpc_connection(args.device)
        except ValueError as e:
            print(e)
            sys.exit(1)

        send_message(connection, "Iteralign Connected to MinKNOW", Severity.WARN)

        logger.info("Loaded RPC")
        while parse_message(connection.acquisition.current_status())['status'] != "PROCESSING":
            time.sleep(1)
        #### Check if we know where data is being written to , if not... wait
        args.watch = parse_message(connection.acquisition.get_acquisition_info())['config_summary']['reads_directory']

    else:
        messageport = ""


    event_handler = FastqHandler(args,logging,messageport,connection)
    # This block handles the fastq
    observer = Observer()
    observer.schedule(event_handler, path=args.watch, recursive=True)
    observer.daemon = True




    try:

        observer.start()
        logger.info("FastQ Monitoring Running.")
        while 1:
            time.sleep(1)

    except KeyboardInterrupt:

        logger.info("Exiting - Will take a few seconds to clean up!")

        observer.stop()
        observer.join()

        os._exit(0)


