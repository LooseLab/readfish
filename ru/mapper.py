import mappy as mp
import time
import threading

# a = mp.Aligner("test/MT-human.fa")  # load or build index
# if not a: raise Exception("ERROR: failed to load/build index")
# s = a.seq("MT_human", 100, 200)     # retrieve a subsequence from the index
# print(mp.revcomp(s))                # reverse complement
# for name, seq, qual in mp.fastx_read("test/MT-orang.fa"): # read a fasta/q sequence
#        for hit in a.map(seq): # traverse alignments
#                print("{}\t{}\t{}\t{}".format(hit.ctg, hit.r_st, hit.r_en, hit.cigar_str))


class MappingServer:
    """
    This class exists to provide a stable list of references to map against.
    The class should exist in perpetuity and ensure that we only ever have one instance of a reference loaded in memory.
    """

    def __init__(self):
        self.references = set()  # An index of all references available
        self.coverage = (
            dict()
        )  # A holder which will track coverage of each sequence in a reference
        self.mappingobjects = dict()
        self.interval = 1800  # Check every 30 minutes to see if a reference has been used - delete it if it hasn't been used.
        self.cov_target = 0

        databasemonitor = threading.Thread(target=self.databasemonitor, args=())
        databasemonitor.daemon = True  # Daemonize thread
        databasemonitor.start()
        # self.references.add("camel")

    def set_cov_target(self, coverage):
        self.cov_target = coverage

    def get_cov_target(self):
        return self.cov_target

    def check_complete(self):
        return len(self.coverage) == len(self.target_coverage().keys())

    def databasemonitor(self):
        while True:
            print("checking references")
            poplist = list()
            print(self.references)
            for reference in self.mappingobjects:
                print(reference)
                if (
                    self.mappingobjects[reference]["last_used"]
                    < time.time() - self.interval
                ):
                    print("This reference is old.")
                    poplist.append(reference)
                else:
                    print("This reference is OK.")
            for reference in poplist:
                # Delete order important here. Removing from the reference list prevents you trying to map something as it is removed.
                self.delete_reference(reference)
                self.mappingobjects.pop(reference)

            time.sleep(self.interval)

    def add_reference(self, reference, filepath):
        """
        Add a reference to the available set of references.
        :param reference: a string demarking a reference
        :return:
        """
        if reference not in self.references:
            self.references.add(reference)
            self.load_index(reference, str(filepath))

    def add_ref_coverage(self, refname, reflen):
        """
        Adds a specific reference name to the coverage dictionary if it isn't already there.
        This assumes that only one user is connecting to the system and tracking coverage.
        :param refname: name of reference being added to the dictionary
        :return:
        """
        if refname not in self.coverage:
            self.coverage[refname] = dict()
            self.coverage[refname]["bases"] = 0
            self.coverage[refname]["length"] = reflen

    def increment_ref_coverage(self, refname, maplen):
        """
        Updates the coverage dictionary for a specific reference element
        :param refname: the index name for the sequence
        :param reflen: the length of the sequence
        :param maplen: the length of the mapping
        :return:
        """
        self.coverage[refname]["bases"] += maplen
        # self.coverage[refname]["length"]=reflen

    def report_coverage(self):
        coverage_results = []
        for refname in self.coverage:
            if self.coverage[refname]["length"] > 0:
                coverage_results.append(
                    {
                        "refname": refname,
                        "bases": self.coverage[refname]["bases"],
                        "coverage": self.coverage[refname]["bases"]
                        / self.coverage[refname]["length"],
                    }
                )
        return coverage_results

    def target_coverage(self):
        """
        Return targets covered by at least the targetvalue
        Parameters
        ----------
        targetvalue

        Returns
        -------

        """
        coverage_results = dict()
        for refname in self.coverage:
            if self.coverage[refname]["length"] > 0:
                if (
                    self.coverage[refname]["bases"] / self.coverage[refname]["length"]
                    >= self.cov_target
                ):
                    coverage_results[refname] = (
                        self.coverage[refname]["bases"]
                        / self.coverage[refname]["length"]
                    )
        return coverage_results

    def delete_reference(self, reference):
        """
        Remove a reference from the available set of references.
        :param reference: a string demarking a reference
        :return:
        """
        self.references.remove(reference)

    def list_references(self):
        return self.references

    def valid(self, ref_name):
        if ref_name in self.references:
            return True

    def load_index(self, reference, filepath):
        self.mappingobjects[reference] = dict()
        self.mappingobjects[reference]["reference"] = mp.Aligner(
            filepath,
            preset="map-ont",
        )
        self.mappingobjects[reference]["last_used"] = time.time()
        for refname in self.mappingobjects[reference]["reference"].seq_names:
            self.add_ref_coverage(
                refname, len(self.mappingobjects[reference]["reference"].seq(refname))
            )
            # print (len(self.mappingobjects[reference]["reference"].seq(refname)))
            # print (refname)
        # print (self.coverage)
        # print (len(self.coverage))

    def map_sequence(self, reference, sequence, trackcov=True):
        """
        This is a fast mapper that takes a sequence and returns the mapped sequence.
        :param reference: index into the reference dictionary
        :param sequence: list of sequences
        :return: list of map objects
        """
        self.refresh_index(reference)
        results = list()
        for hit in self.mappingobjects[reference]["reference"].map(
            sequence["sequence"]
        ):
            results.append(
                "{}\t{}\t{}".format(sequence["read_id"], len(sequence["sequence"]), hit)
            )
            if trackcov:
                #### How do we handle multiple hits?
                # print ("updating coverage {} {}".format(hit.ctg,hit.mlen))
                self.increment_ref_coverage(hit.ctg, hit.mlen)
        # print(self.report_coverage())
        return results

    def refresh_index(self, reference):
        self.mappingobjects[reference]["last_used"] = time.time()
