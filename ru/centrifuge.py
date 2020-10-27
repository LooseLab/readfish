"""
A helper function to provide a class that can run centrifuge and return results as required by iteralign
"""
import subprocess
import csv
import urllib.request as request
import urllib.error as url_error
from io import StringIO, BytesIO
import gzip
from Bio import SeqIO
import logging
import logging.handlers


class CentrifugeServer:
    """
    Long term goal is that this will allow streaming of individual reads or chunks of reads to a continuously open centrifuge classifier.
    """

    def __init__(
        self,
        threshold=0,
        plasmids=None,
        csummary=None,
        path=None,
        prefix=None,
        gfasta=None,
        seqlength=5000,
        references=None,
        toml=None,
        threads=1,
        cindex=None,
        creport=None,
    ):
        self.logger = logging.getLogger("CentrifugeServer")
        self.logger.info("Configuring Centrifuge Server.")
        self.tax_data = dict()
        self.threshold = threshold
        self.new_targets = list()
        self.all_targets = set()
        self.ref_lookup = dict()
        self.plasmids_dict = dict()
        self.plasmids = plasmids
        self.csummary = csummary
        self.path = path
        self.prefix = prefix
        self.gfasta = gfasta
        self.seqlength = seqlength
        self.references = references
        self.toml = toml
        self.threads = threads
        self.cindex = cindex
        self.creport = creport
        self._store_urls()
        if self.plasmids:
            self.plasmids_dict = self._store_plasmids()
        # ToDO Do we need this? Perhaps - it accepts a list of sequences that you might want to reject up front.
        if self.references:
            for taxID in self.references:
                self.new_targets.append(str(taxID))

    def _store_plasmids(self):
        r = ("name", "path")
        with open(self.csummary) as f:
            d = {
                int(x[0]): dict(zip(r, x[1:]))
                for i, l in enumerate(f)
                for x in (l.strip().split("\t"),)
                if i > 0
            }
        return d

    def _store_urls(self):
        with open(self.csummary, newline="") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                taxID, name, url = row[0].split("\t")
                self.ref_lookup[taxID] = url

    def _download_references(self, taxID):
        lengths = {}
        link = self.ref_lookup[taxID]
        self.logger.info("Attempting to download: {}".format(link))
        try:
            response = request.urlopen(link)
        except url_error.URLError as e:
            self.logger.debug(e)
            self.logger.debug("Closing script")

        compressed_file = BytesIO(response.read())
        with gzip.open(compressed_file, "rt") as fh, gzip.open(
            self.path + self.prefix + self.gfasta, "at"
        ) as fasta_seq:
            for seq_record in SeqIO.parse(fh, "fasta"):
                if len(seq_record) > self.seqlength:
                    lengths[seq_record.id] = len(seq_record)
                    SeqIO.write(seq_record, fasta_seq, "fasta")

        if self.plasmids:
            self.logger.info(
                "Obtaining the plasmids for the following taxids: {}".format(taxID)
            )

            with gzip.open(self.plasmids, "rt") as fh, gzip.open(
                self.path + self.prefix + self.gfasta, "at"
            ) as fasta_seq:
                for seq_record in SeqIO.parse(fh, "fasta"):
                    if taxID in self.plasmids_dict.keys():
                        if (
                            self.plasmids_dict[taxID]["name"] in seq_record.description
                            and len(seq_record) > self.seqlength
                        ):
                            lengths[seq_record.id] = len(seq_record)
                            SeqIO.write(seq_record, fasta_seq, "fasta")
        self.logger.info("Genome file generated in {}".format(fasta_seq))
        return lengths

    def _add_taxon(self, taxID, name, genomeSize, numUniqueReads):
        if taxID not in self.tax_data.keys():
            self.tax_data[taxID] = dict()
            self.tax_data[taxID]["name"] = name
            self.tax_data[taxID]["genomeSize"] = genomeSize
            self.tax_data[taxID]["uniqueReads"] = int(numUniqueReads)
        else:
            self.tax_data[taxID]["uniqueReads"] += int(numUniqueReads)

    def _calculate_targets(self):
        for taxID in self.tax_data:
            if (
                taxID not in self.all_targets
                and self.tax_data[taxID]["uniqueReads"] >= self.threshold
            ):
                self.new_targets.append(taxID)
                self.all_targets.add(taxID)

    def classify(self, fastqfileList, mapper):
        # convert the 'fastqfileList' into a string valid for the list of fastq files to be read by centrifuge
        fastq_str = ",".join(fastqfileList)
        if self.toml["conditions"]["reference"]:
            self.logger.info(
                "Reference is {}.".format(self.toml["conditions"]["reference"])
            )
        else:
            self.logger.info("No reference yet loaded.")
        # centrifuge command to classify reads in the fastq files found by watchdog
        centrifuge_cmd = "centrifuge -p {} -x {} -q {} --report-file {}".format(
            self.threads, self.cindex, fastq_str, self.creport
        )
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
        # First grab and store information on the genomes seen.
        # ToDo: Do we need to keep this? Why are we opening this file?
        with open(self.creport, newline="") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                # print(row)
                (
                    name,
                    taxID,
                    taxRank,
                    genomeSize,
                    numReads,
                    numUniqueReads,
                    abundance,
                ) = row[0].split("\t")
                self._add_taxon(taxID, name, genomeSize, numUniqueReads)
        """
        #This bit of code is only needed if we need access to the readIDs - which we do not!
        for line in out.splitlines()[1:-1]:
            #print (line)
            readID, seqID, taxID, score , secondBestScore, hitLength,queryLength, numMatches= line.split("\t")
            if numMatches == 1: #this filters out reads that map to one or more genomes
                print (readID,numMatches,taxID)
        """
        # print (self.tax_data)
        self._calculate_targets()

        ### So if we have new targets we need to download the references and get them for building an index.
        if self.new_targets:
            while len(self.new_targets) > 0:
                target = self.new_targets.pop()
                self.logger.info(self._download_references(target))
            # Make a new reference
            mapper.load_index("test", self.path + self.prefix + self.gfasta)
            self.toml["conditions"]["reference"] = self.path + self.prefix + self.gfasta
            self.logger.info(
                "Updated reference is {}".format(self.toml["conditions"]["reference"])
            )
        return self.toml["conditions"]["reference"]
