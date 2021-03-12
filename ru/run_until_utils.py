import logging
import logging.handlers
import os
import gzip
import toml
import threading
import time
from watchdog.events import FileSystemEventHandler
from ru.mapper import MappingServer as Map
from ru.centrifuge import CentrifugeServer
from ru.utils import nice_join, send_message, Severity


def file_dict_of_folder_simple(path):
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

    logger.info(
        "found %d existing fastq files to process first." % (len(file_list_dict))
    )

    return file_list_dict


def write_new_toml(args, targets):
    for k in args.toml["conditions"].keys():
        curcond = args.toml["conditions"].get(k)
        if isinstance(curcond, dict):

            # newtargets = targets
            # newtargets.extend(curcond["targets"])

            # newtargets = list(dict.fromkeys(newtargets))
            # curcond["targets"]=list(set(newtargets))
            curcond["targets"] = targets

    with open("{}_live".format(args.tomlfile), "w") as f:
        toml.dump(args.toml, f)


###Function modified from https://raw.githubusercontent.com/lh3/readfq/master/readfq.py


def readfq(fp):  # this is a generator function
    last = None  # this is a buffer keeping the last unprocessed line
    while True:  # mimic closure; is it a bad idea?
        if not last:  # the first record or a record following a fastq
            for l in fp:  # search for the start of the next record
                if l[0] in ">@":  # fasta/q header line
                    last = l[:-1]  # save this line
                    break
        if not last:
            break
        desc, name, seqs, last = last[1:], last[1:].partition(" ")[0], [], None
        for l in fp:  # read the sequence
            if l[0] in "@+>":
                last = l[:-1]
                break
            seqs.append(l[:-1])
        if not last or last[0] != "+":  # this is a fasta record
            yield desc, name, "".join(seqs), None  # yield a fasta record
            if not last:
                break
        else:  # this is a fastq record
            seq, leng, seqs = "".join(seqs), 0, []
            for l in fp:  # read the quality
                seqs.append(l[:-1])
                leng += len(l) - 1
                if leng >= len(seq):  # have read enough quality
                    last = None
                    yield desc, name, seq, "".join(seqs)  # yield a fastq record
                    break
            if last:  # reach EOF before reading enough quality
                yield desc, name, seq, None  # yield a fasta record instead
                break


def fastq_results(fastq):
    if fastq.endswith(".gz"):

        with gzip.open(fastq, "rt") as fp:
            try:
                for desc, name, seq, qual in readfq(fp):
                    yield desc, name, seq, qual

            except Exception as e:
                print(e)
    else:
        with open(fastq, "r") as fp:
            try:
                # now = time.time()
                for desc, name, seq, qual in readfq(fp):
                    yield desc, name, seq, qual

            except Exception as e:
                print(e)


class FastqHandler(FileSystemEventHandler):
    def __init__(self, args, rpc_connection):
        self.args = args
        # self.messageport = messageport
        self.connection = rpc_connection
        self.logger = logging.getLogger("FastqHandler")
        self.running = True
        self.fastqdict = dict()
        self.creates = file_dict_of_folder_simple(self.args.watch)
        self.t = threading.Thread(target=self.processfiles)

        try:
            self.t.start()
        except KeyboardInterrupt:
            self.t.stop()
            raise

    def on_created(self, event):
        """Watchdog counts a new file in a folder it is watching as a new file"""
        """This will add a file which is added to the watchfolder to the creates and the info file."""
        # if (event.src_path.endswith(".fastq") or event.src_path.endswith(".fastq.gz")):
        #     self.creates[event.src_path] = time.time()

        # time.sleep(5)
        if (
            event.src_path.endswith(".fastq")
            or event.src_path.endswith(".fastq.gz")
            or event.src_path.endswith(".fq")
            or event.src_path.endswith(".fq.gz")
        ):
            self.logger.info("Processing file {}".format(event.src_path))
            self.creates[event.src_path] = time.time()

    def on_modified(self, event):
        if (
            event.src_path.endswith(".fastq")
            or event.src_path.endswith(".fastq.gz")
            or event.src_path.endswith(".fq")
            or event.src_path.endswith(".fq.gz")
        ):
            self.logger.info("Processing file {}".format(event.src_path))
            self.logger.debug("Modified file {}".format(event.src_path))
            self.creates[event.src_path] = time.time()

    def on_moved(self, event):
        if any(
            (
                event.dest_path.endswith(".fastq"),
                event.dest_path.endswith(".fastq,gz"),
                event.dest_path.endswith(".gq"),
                event.dest_path.endswith(".fq.gz"),
            )
        ):
            self.logger.info("Processing file {}".format(event.dest_path))
            self.logger.debug("Modified file {}".format(event.dest_path))
            self.creates[event.dest_path] = time.time()


class FastQMonitor(FastqHandler):
    def __init__(
        self, args, rpc_connection, centrifuge=False, mapper=False, rununtil=False
    ):
        if centrifuge:
            self.centrifuge = CentrifugeServer(
                threshold=args.threshold,
                plasmids=args.plasmids,
                csummary=args.csummary,
                path=args.path,
                prefix=args.prefix,
                gfasta=args.gfasta,
                seqlength=args.seqlength,
                references=args.references,
                toml=args.toml,
                threads=args.threads,
                cindex=args.cindex,
                creport=args.creport,
            )
        else:
            self.centrifuge = None
        if mapper:
            self.mapper = Map()
            self.mapper.set_cov_target(args.depth)
        else:
            self.mapper = None
        self.rununtil = rununtil
        super().__init__(args=args, rpc_connection=rpc_connection)

    def processfiles(self):
        self.logger.info("Process Files Initiated")
        self.counter = 0
        self.targets = []

        while self.running:
            currenttime = time.time()

            fastqfilelist = list()
            for fastqfile, createtime in sorted(
                self.creates.items(), key=lambda x: x[1]
            ):

                delaytime = 0

                # file created 5 sec ago, so should be complete. For simulations we make the time longer.
                if int(createtime) + delaytime < time.time():
                    self.logger.info(fastqfile)
                    del self.creates[fastqfile]
                    self.counter += 1
                    fastqfilelist.append(fastqfile)

                    # print (fastqfile,md5Checksum(fastqfile), "\n\n\n\n")
            # as long as there are files within the args.watch directory to parse
            if fastqfilelist:
                parse_fastq_file(
                    fastqfilelist,
                    self.args.toml["conditions"]["reference"],
                    self.mapper,
                    self.centrifuge,
                )
                # This prints those targets with a coverage greater than the threshold set in the arguments
                if self.mapper:
                    targets = self.mapper.target_coverage().keys()
                    print(self.mapper.report_coverage())
                    if len(targets) > len(self.targets):
                        updated_targets = set(targets) - set(self.targets)
                        update_message = "Updating targets with {}".format(
                            nice_join(updated_targets, conjunction="and")
                        )
                        self.logger.info(update_message)
                        if not self.args.simulation:
                            send_message(self.connection, update_message, Severity.WARN)
                        write_new_toml(self.args, targets)
                        self.targets = []
                        self.targets = targets

                    if len(self.targets) > 0 and self.mapper.check_complete():

                        self.logger.info(
                            "Every target is covered at at least {}x".format(
                                self.args.depth
                            )
                        )
                        if not self.args.simulation:
                            if self.rununtil:
                                self.connection.protocol.stop_protocol()
                                send_message(
                                    self.connection,
                                    "ReadFish has stopped the run as all targets should be covered by at least {}x".format(
                                        self.args.depth
                                    ),
                                    Severity.WARN,
                                )
                            else:
                                send_message(
                                    self.connection,
                                    "ReadFish reports all current targets should be covered by at least {}x".format(
                                        self.args.depth
                                    ),
                                    Severity.WARN,
                                )

            if currenttime + 5 > time.time():
                time.sleep(5)


def parse_fastq_file(fastqfilelist, reference_loc, mapper, centrifuge):
    logger = logging.getLogger("ParseFastq")
    with open(os.devnull, "w") as devnull:
        # This function will classify reads and update the mapper if it needs doing so.
        if centrifuge:
            logger.info("Running Centrifuge")
            reference_loc = centrifuge.classify(fastqfilelist, mapper)
        if mapper:
            if reference_loc:
                logger.info("Mapping with {}.".format(reference_loc))
                mapper.add_reference("test", reference_loc)
                for file in fastqfilelist:
                    for desc, name, seq, qual in fastq_results(file):
                        sequence_list = {"sequence": seq, "read_id": name}
                        mapper.map_sequence("test", sequence_list)
