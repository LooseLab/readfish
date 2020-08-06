"""
Iteralign-centrifuge.
Design spec.
    1. Grab fastq files from a location.
    2. Classify reads that uniquely align to a reference genome.
    3. Generate a minimap2 index from the previously found reference genomes.
    4. Align the files ONCE to a reference.
    5. Calculate cumulative coverage information.
    6. Write a list of genomes that are covered at a particular threshold.
    7. Rinse and repeat
"""
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time

from io import StringIO, BytesIO
import gzip

import argparse
from pathlib import Path
import shutil
import urllib.request as request
import urllib.error as url_error
from contextlib import closing

import pandas as pd
import toml
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver as Observer

from ru.arguments import get_parser
from ru.utils import nice_join, print_args, send_message, Severity
from read_until_api_v2.load_minknow_rpc import get_rpc_connection, parse_message

from Bio import SeqIO
from collections import defaultdict

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)-20s - %(message)s"
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
DEFAULT_COVERAGE_DEPTH = 30
DEFAULT_PERCENTAGE_COVERED = 0.99
DEFAULT_CORES = 2

DEFAULT_THRESHOLD = 2000
DEFAULT_PREFIX = "iteraligncentrifuge"
DEFAULT_REJECT = "reject.tsv"
DEFAULT_CREPORT = "centrifuge_report.tsv"
DEFAULT_READS = "out.tsv"
DEFAULT_MINDEX = "mindex.mmi"
DEFAULT_GENOME = "genome.fna.gz"
DEFAULT_TIDFILE = "taxids.toml"
DEFAULT_COVERAGE_FILE = "coverage.tsv"
DEFAULT_SEQUENCE_LENGTH = 100000




def get_fq(s, pattern="*.fq"):
    return [str(f) for f in Path(s).rglob(pattern)]


_help = "ReadFish and Run Until, using centrifuge"
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
        "--device",
        dict(
            required=True,
            action="store",
            help="The sequencing position being addressed"
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
        "--cindex",
        dict(
            required=True,
            action="store",
            help="The centrifuge index required for read alignment. Must only have the prefix of the index names before the full stop and number of each index",
        ),
    ),
    (
        "--readfile",
        dict(
            action="store",
            help="The name of the file that will contain the metrics for the reads analysed",
            default=DEFAULT_READS,
        ),
    ),
    (
        "--csummary",
        dict(
            required=True,
            action="store",
            help="The file path to the custom centrifuge summary file with the ftp path for the reference genomes",
        ),
    ),
    (
        "--gfasta",
        dict(
            action="store",
            help="The file name for the genome references downloaded after centrifuge identification",
            default=DEFAULT_GENOME,
        ),
    ),
    (
        "--creport",
        dict(
            action="store",
            help="The file name of the centrifuge report file 'centrifuge_report.tsv' made each iteration. Will be created in this scripts source directory",
            default=DEFAULT_CREPORT,
        ),
    ),
    (
        "--keepfiles",
        dict(
            action="store_true",
            help="Set argument to retain the files generated by the centrifuge section of the script"
        ),
    ),
    (
        "--reject",
        dict(
            action="store",
            help="The file name containing reads not utilised within the 'call' file and the reason why.",
            default=DEFAULT_REJECT
        ),
    ),
    (
        "--mindex",
        dict(
            action="store",
            help="The file name where the minimap index will be stored",
            default=DEFAULT_MINDEX,
        ),
    ),
    (
        "--tidfile",
        dict(
            action="store",
            help="The file name where the taxIDs found with centrifuge are stored with the iteration they were found",
            default=DEFAULT_TIDFILE,
        ),
    ),
    (
        "--prefix",
        dict(
            action="store",
            help="The file path and prefix for all files generated by this script will generate",
            default=DEFAULT_PREFIX,
        ),
    ),
    (
        "--path",
        dict(
            required=True,
            action="store",
            help="The directory path where all files generated by this script will be stored"
        ),
    ),
    (
        "--threshold",
        dict(
            action="store",
            help="The threshold number of reads that are classified before a reference genome is added to the mmi",
            default=DEFAULT_THRESHOLD,
            type=int,
        ),
    ),
    (
        "--plasmids",
        dict(
            action="store",
            help="The path and file name of the plasmid file that will be used by the script",
        ),
    ),
    (
        "--references",
        dict(
            action="store",
            help="At least 1 taxID must be provided to be downloaded for mmi generation.",
            nargs="+",
            type=int,
        ),
    ),
    (
        "--seqlength",
        dict(
            action="store",
            help="The threshold length of an assembly to be incorporated into the reference file",
            default=DEFAULT_SEQUENCE_LENGTH,
            type=int,
        ),
    ),
    (
        "--coveragefile",
        dict(
            action="store",
            help="the file suffix containing 3 tab separated columns: iteration, referenceid, coverage (percent)",
            default=DEFAULT_COVERAGE_FILE,
        ),
    ),
    (
        "--toml",
        dict(
            metavar="TOML",
            required=True,
            help="The magic TOML file that will save your life?",
            # type=toml.load,
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

                if f.endswith(".fastq") or f.endswith(".fastq.gz") or f.endswith(".fq") or f.endswith(".fq.gz"):

                    logger.debug("Processing File {}\r".format(f))
                    filepath = os.path.join(path, f)
                    file_list_dict[filepath] = os.stat(filepath).st_mtime

    logger.info("processed %s files" % (counter))

    logger.info("found %d existing fastq files to process first." % (len(file_list_dict)))

    return file_list_dict


def url_list_generation(args,difference_set):
    # read in the file with taxIDs and their corresponding reference genome
    summary_centrifuge = pd.read_csv(args.csummary,
                                     sep="\t",
                                     )

    # create a set of ftp urls based on matching taxIDs between 'difference_set' and 'summary_centrifuge''
    url_list = list(summary_centrifuge[summary_centrifuge["taxid"].isin(difference_set)]["fasta_path"])

    return url_list


def download_references(args, url_list, taxid_set):

    lengths = {}
    for link in url_list:
        print("Attempting to download: {}".format(link), end="\n")
        try:
            response = request.urlopen(link)
        except url_error.URLError as e:
            print(e)
            print("Closing script")
            break
        compressed_file = BytesIO(response.read())
        with gzip.open(compressed_file, "rt") as fh, gzip.open(args.path + args.prefix + args.gfasta, "at") as fasta_seq:
            for seq_record in SeqIO.parse(fh, "fasta"):
                if len(seq_record) > args.seqlength:
                    lengths[seq_record.id] = len(seq_record)
                    SeqIO.write(seq_record, fasta_seq, "fasta")

    if args.plasmids:
        r = ("name", "path")
        logging.info("Obtaining the plasmids for the following taxids: {}".format(taxid_set))
        with open(args.csummary) as f:
            d = {int(x[0]): dict(zip(r, x[1:])) for i, l in enumerate(f) for x in (l.strip().split("\t"),)
                 if i > 0}

            for taxid in taxid_set:
                with gzip.open(args.plasmids, "rt") as fh, gzip.open(args.path + args.prefix + args.gfasta, "at") as fasta_seq:
                    for seq_record in SeqIO.parse(fh, "fasta"):
                        if d[taxid]["name"] in seq_record.description and len(seq_record) > args.seqlength:
                            lengths[seq_record.id] = len(seq_record)
                            SeqIO.write(seq_record, fasta_seq, "fasta")

    logging.info("Genome file generated")

    return lengths


def generate_mmi(args, counter):
    args.toml['conditions']['reference'] = os.path.abspath("{}{}_{}_{}".format(args.path,args.prefix,counter,args.mindex))
    minimap_cmd = ["minimap2", "-x", "map-ont", "-d", args.toml['conditions']['reference'], args.path + args.prefix + args.gfasta]

    # show the minimap command in the terminal
    logging.info(" ".join(minimap_cmd))

    # subprocess the 'minimap_cmd'
    minimap_db = subprocess.Popen(minimap_cmd,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  stdin=subprocess.PIPE,
                                  universal_newlines=True,
                                  )
    out, err = minimap_db.communicate()

    minimap_db.stdout.close()


def parse_fastq_file(fastqfileList, args, logging, length_dict, taxID_set, counter, coverage_sum, connection):
    logger = logging.getLogger("ParseFastq")
    logger.info(fastqfileList)
    logger.info(args.toml['conditions']['reference'])
    with open(os.devnull, 'w') as devnull:

        # convert the 'fastqfileList' into a string valid for the list of fastq files to be read by centrifuge
        fastq_str = ",".join(fastqfileList)

        # centrifuge command to classify reads in the fastq files found by watchdog
        centrifuge_cmd = "centrifuge -p {} -x {} -q {}".format(args.threads,
                                                               args.cindex,
                                                               fastq_str
                                                               )

        # show what the centrifuge command in the terminal
        logging.info(centrifuge_cmd)

        # start time of centrifuge to track the time centrifuge requires to classify reads
        centrifuge_start_time = time.time()

        # subprocess for 'centrifuge_cmd'
        proc = subprocess.Popen(
            centrifuge_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            shell=True,
            # Aliased by `text=True` in 3.7
            universal_newlines=True,
        )
        out, err = proc.communicate()
        proc.stdout.close()

        # confirm that the centrifuge pipeline has finished and show the time of execusion
        logging.info("Post centrifuge run: {} seconds".format(time.time()-centrifuge_start_time))

        output_fields = ["readID", "seqID", "taxID", "hitLength", "queryLength", "numMatches"]

        # create the DataFrame from the centrifuge output using 'output_fields' as the column headers
        out_df = pd.read_csv(StringIO(out),
                             sep="\t",
                             usecols=output_fields
                             )

        # create a dataframe from the args.creport 'centrifuge_report.tsv'
        report_df = pd.read_csv(args.creport,
                                sep="\t",
                                usecols=["name", "genomeSize", "taxID"],
                                )

        # merge both dataframes together
        new_df = pd.merge(out_df, report_df, on="taxID")

        # only reads that uniquely align to a species will be used, with reads that numMatches != 1 being filtered
        reject_df = new_df[new_df.numMatches != 1]
        reject_df["reason"] = "Multiple reference genome alignments"
        # reject_df.loc[:, "reason"] = "Multiple reference genome alignments"

        # genomeSize == 0 infer a read classification above the species taxon and are therefore removed
        intermediate_df = new_df[new_df.genomeSize == 0]
        intermediate_df = intermediate_df[intermediate_df.numMatches == 1]
        intermediate_df["reason"] = "Read aligns to non-species taxon"

        # log the reads that were removed into a seperate file
        reject_df = reject_df.append(intermediate_df)
        if os.path.isfile(args.path + args.prefix + args.reject):
            reject_df.to_csv(args.path + args.prefix + args.reject,
                             sep="\t",
                             mode="a",
                             index=False,
                             header=None,
                             )
        else:
            reject_df.to_csv(args.path + args.prefix + args.reject,
                             sep="\t",
                             mode="a",
                             index=False,
                             header=True,
                             )

        # reads that uniquely align to one species are logged into a file
        new_df = new_df[new_df.numMatches == 1]
        if os.path.isfile(args.path + args.prefix + args.readfile):
            new_df.to_csv(args.path + args.prefix + args.readfile,
                          sep="\t",
                          mode="a",
                          index=None,
                          header=None,
                          )
        else:
            new_df.to_csv(args.path + args.prefix + args.readfile,
                          sep="\t",
                          mode="a",
                          index=None,
                          header=True,
                          )
        logging.info("reject file made")

        # read in all valid reads back into memory from all current iterations
        all_reads_df = pd.read_csv(args.path + args.prefix + args.readfile,
                                   sep="\t"
                                   )

        # count the number of reads that were clasified to all taxIDs found within 'all_reads_df' and only keep the taxIDs with a count above args.threshold
        taxid_count = all_reads_df.groupby("taxID").agg({"taxID": "count"})
        taxid_result_set = set(taxid_count[taxid_count["taxID"].ge(args.threshold)].index.values.tolist())
        # call in the taxIDs that already have a reference genome in the mmi
        downloaded_set = taxID_set

        # if taxIDs were found above args.threshold
        if taxid_result_set:
            logging.info("taxIDs found above specified threshold")
            # locate new taxIDs that were not found in previous iterations
            difference_set = taxid_result_set - downloaded_set
            downloaded_set |= taxid_result_set

            # if novel taxIDs were found
            if difference_set:
                with open(args.path + args.prefix + args.tidfile, "w+") as f:
                    d = toml.load(args.path + args.prefix + args.tidfile)
                    if os.path.isfile(args.tidfile):
                        d["taxid"] = {"iteration.{}".format(counter): difference_set}
                    else:
                        d = {"taxid": {"iteration.{}".format(counter): difference_set}}
                    toml.dump(d, f)
                f.close()

                logging.info("new taxids found: {}".format(difference_set))
                logging.info("Downloading reference genomes")

                url_list = url_list_generation(args, difference_set)

                # download the reference genomes into a single file

                length_dict.update(download_references(args, url_list, difference_set))

                logging.info("Generating mmi")

                generate_mmi(args, counter)

                update_message = "Updated the minimap MMI to {}".format(args.toml['conditions']['reference'])
                logging.info(update_message)
                if not args.simulation:
                    #send_message_port(update_message, args.host, messageport)
                    send_message(connection, update_message, Severity.WARN)


            else:
                # show in terminal that no new taxIDs were found
                logging.info("No new taxIDs were identified")
        else:
            logging.info("No taxIDs found above threshold.")
        # all of the new code has been parsed, the rest follows standard 'iteralign.py' script
        logging.info("new code parsing completed\n\ncommencing iteralign")

        minimapcmd = ["minimap2","-ax","map-ont","-t {}".format(args.threads),args.toml['conditions']['reference']] #" ".join(fastqfilelist)]
        minimapcmd.extend(fastqfileList)
        logging.info(" ".join(minimapcmd))
        minimapoutput = subprocess.Popen(minimapcmd, stdout=subprocess.PIPE,stderr=devnull)

        samcmd = ["samtools","view", "-bS"]
        samoutput = subprocess.Popen(samcmd, stdin=minimapoutput.stdout, stdout=subprocess.PIPE, stderr=devnull)
        #samsortcmd = ["samtools", "sort", "-@2", "-o", "sortedbam.bam"]
        samsortcmd = ["samtools", "sort", "-@{}".format(args.threads)]
        samsortoutput = subprocess.Popen(samsortcmd, stdin=samoutput.stdout, stdout=subprocess.PIPE, stderr=devnull)
        samdepthcmd = ["samtools", "depth", "/dev/stdin"]
        samdepthoutput = subprocess.Popen(samdepthcmd, stdin=samsortoutput.stdout,stdout=subprocess.PIPE, stderr=devnull, universal_newlines=True)
        minimapoutput.stdout.close()
        samoutput.stdout.close()
        samsortoutput.stdout.close()

        iter_depth = (l.strip().split("\t") for l in samdepthoutput.stdout)
        parse_iter = ((x[0], int(x[-1])) for x in iter_depth)

        d = defaultdict(int)
        d.update(coverage_sum)
        for name, depth in parse_iter:
            d[name] += depth

        depth_dict = {k: d[k]/length_dict[k] for k in length_dict.keys() & d}

        with open(args.path + args.prefix + args.coveragefile, "a") as fh:
            for k, v in depth_dict.items():
                fh.write("{}\t{}\t{}\n".format(counter, k, v))

        targets = [k for k, v in depth_dict.items() if v > args.depth]

        logging.info(targets)

        counter += 1

        logging.info("Finished processing {}.".format(" ".join(fastqfileList)))

    return targets, downloaded_set, counter, d


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

    def __init__(self, args, logging, messageport, rpc_connection):
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
        self.counter = 1
        self.targets = []
        self.masterdf = pd.DataFrame(columns=['seqid', 'position', 'coverage'])
        self.taxid_entries = 0
        self.downloaded_set = set()
        self.length_dict = {}
        self.coverage_sum = {}

        if self.args.references:
            logging.info("References argument provided. Will download references genomes.")
            self.downloaded_set = set(self.args.references)
            logging.info(self.downloaded_set)
            self.url_list = url_list_generation(self.args, self.args.references)
            self.length_dict.update(download_references(self.args, self.url_list, self.downloaded_set))
            generate_mmi(self.args, self.counter)


        while self.running:
            currenttime = time.time()
            # for fastqfile, createtime in tqdm(sorted(self.creates.items(), key=lambda x: x[1])):
            fastqfilelist = list()
            for fastqfile, createtime in sorted(self.creates.items(), key=lambda x: x[1]):

                delaytime = 0

                # file created 5 sec ago, so should be complete. For simulations we make the time longer.
                if (int(createtime) + delaytime < time.time()):
                    self.logger.info(fastqfile)
                    del self.creates[fastqfile]
                    self.counter += 1
                    fastqfilelist.append(fastqfile)

                    # print (fastqfile,md5Checksum(fastqfile), "\n\n\n\n")
            # as long as there are files within the args.watch directory to parse
            if fastqfilelist:
                print(self.downloaded_set)
                targets, self.downloaded_set, self.taxid_entries, self.coverage_sum = parse_fastq_file(fastqfilelist, self.args, logging, self.length_dict, self.downloaded_set, self.taxid_entries, self.coverage_sum, self.connection)
                print(targets)
                print(self.targets)

                if len(targets) > len(self.targets):
                    updated_targets = set(targets) - set(self.targets)
                    update_message = "Updating targets with {}".format(nice_join(updated_targets, conjunction="and"))
                    self.logger.info(update_message)
                    if not self.args.simulation:
                        #send_message_port(update_message, self.args.host, self.messageport)
                        send_message(self.connection, update_message, Severity.WARN)
                    write_new_toml(self.args, targets)
                    self.targets = []
                    self.targets = targets.copy()

                if self.masterdf.shape[0] > 0 and self.masterdf.shape[0] == len(self.targets):
                    # Every target is covered at the desired coverage level.
                    self.logger.info("Every target is covered at at least {}x".format(self.args.depth))
                    if not self.args.simulation:
                        self.connection.protocol.stop_protocol()
                        #send_message_port(
                        #    "Iter Align has stopped the run as all targets should be covered by at least {}x".format(
                        #        self.args.depth), self.args.host, self.messageport)
                        send_message(self.connection, "Iter Align has stopped the run as all targets should be covered by at least {}x".format(
                                self.args.depth), Severity.WARN)

                # parse_fastq_file(fastqfile, self.rundict, self.fastqdict, self.args, self.header, self.MinotourConnection)

                # self.args.files_processed += 1

                if currenttime + 5 > time.time():
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
        "This entry point is deprecated, please use 'readfish centrifuge' instead"
    )

def run(parser, args):
    # new code block: change the reference path within the args.toml file into the args.mindex path
    d = toml.load(args.toml)

    print(d["conditions"]["reference"])
    args.tomlfile = args.toml
    args.toml = toml.load(args.toml)
    print(args)

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

    #set default message severity level.
    severity = 2

    if args.watch is None:
        args.simulation = False
        logger.info("Creating rpc connection for device {}.".format(args.device))
        try:
            connection, messageport = get_rpc_connection(args.device)
        except ValueError as e:
            print(e)
            sys.exit(1)

        #send_message_port("Iteralign Connected to MinKNOW", args.host, messageport)
        send_message(connection, "Iteralign Connected to MinKNOW.", Severity.WARN)

        logger.info("Loaded RPC")
        while parse_message(connection.acquisition.current_status())['status'] != "PROCESSING":
            time.sleep(1)
        ### Check if we know where data is being written to , if not... wait
        args.watch = parse_message(connection.acquisition.get_acquisition_info())['config_summary'][
            'reads_directory']

    else:
        messageport = ""

    event_handler = FastqHandler(args, logging, messageport, connection)
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

        if args.keepfiles:
            logging.info("The 'keepfiles' argument was set, files generated by classifier have been retained")
        else:
            if os.path.isdir(args.path):
                for path, dirs, files in os.walk(args.path):
                    for f in files:
                        if f.startswith(args.prefix):
                            os.unlink(f)
                            logging.info("file removed: {}".format(f))

            if os.path.isdir("./"):
                for path, dirs, files in os.walk("./"):
                    for f in files:
                        if f.endswith(args.creport):
                            os.unlink(f)
                            logging.info("file removed: {}".format(f))

        logging.info("All files generated by classifier have been removed.")

        os._exit(0)


if __name__ == "__main__":
    main()
