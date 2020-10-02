"""summarise_fq.py
todo refactor
Summarises fastq statistics about fastq files written out by a read until experiment.
"""
import gzip
from pathlib import Path
from statistics import mean, median, stdev
from collections import defaultdict
import sys

import toml
import mappy as mp


_help = "Summary stats from FASTQ files"
_cli = (
    (
        "toml",
        dict(help="TOML configuration file"),
    ),
    (
        "dir",
        dict(help="Called files from the ReadFish experiment"),
    ),
)


def readfq(fp):  # this is a generator function
    """Read FASTA/Q records from file handle
    https://github.com/lh3/readfq/blob/091bc699beee3013491268890cc3a7cbf995435b/readfq.py
    """
    last = None  # this is a buffer keeping the last unprocessed line
    while True:  # mimic closure; is it a bad idea?
        if not last:  # the first record or a record following a fastq
            for l in fp:  # search for the start of the next record
                if l[0] in ">@":  # fasta/q header line
                    last = l[:-1]  # save this line
                    break
        if not last:
            break
        name, seqs, last = last[1:].partition(" ")[0], [], None
        for l in fp:  # read the sequence
            if l[0] in "@+>":
                last = l[:-1]
                break
            seqs.append(l[:-1])
        if not last or last[0] != "+":  # this is a fasta record
            yield name, "".join(seqs), None  # yield a fasta record
            if not last:
                break
        else:  # this is a fastq record
            seq, leng, seqs = "".join(seqs), 0, []
            for l in fp:  # read the quality
                seqs.append(l[:-1])
                leng += len(l) - 1
                if leng >= len(seq):  # have read enough quality
                    last = None
                    yield name, seq, "".join(seqs)
                    # yield a fastq record
                    break
            if last:  # reach EOF before reading enough quality
                yield name, seq, None  # yield a fasta record instead
                break


def get_fq(directory):
    types = ([".fastq"], [".fastq", ".gz"], [".fq"], [".fq", ".gz"])
    files = (
        str(p.resolve()) for p in Path(directory).glob("**/*") if p.suffixes in types
    )
    yield from files


def icumsum(arr):
    total = 0
    for i, x in enumerate(arr):
        total += x
        yield i, total


def N50(arr):
    if not isinstance(arr, list):
        arr = list(arr)
    arr.sort()
    s = sum(arr)
    return int(arr[[i for i, c in icumsum(arr) if c >= s * 0.5][0]])


def main():
    sys.exit("This entry point is deprecated, please use 'readfish summary' instead")


def run(parser, args):
    t = toml.load(args.toml)
    reference = t["conditions"].get("reference", "")

    if not Path(reference).is_file():
        raise FileNotFoundError("reference file not found at: {}".format(reference))

    mapper = mp.Aligner(reference, preset="map-ont")

    print("Using reference: {}".format(reference), file=sys.stderr)

    pre_res = defaultdict(list)

    for f in get_fq(args.dir):
        if f.endswith(".gz"):
            fopen = gzip.open
        else:
            fopen = open

        with fopen(f, "rt") as fh:
            for name, seq, _ in readfq(fh):
                # Map seq, only use first mapping (a bit janky)
                for r in mapper.map(seq):
                    pre_res[r.ctg].append(len(seq))
                    break

    header = [
        "contig",
        "number",
        "sum",
        "min",
        "max",
        "std",
        "mean",
        "median",
        "N50",
    ]
    res = [header]
    for ctg, data in sorted(pre_res.items()):
        if len(data) < 2:
            print("Skipping contig {}, too few mappings".format(ctg), file=sys.stderr)
            continue
        res.append(
            [
                ctg,
                "{:.0f}".format(len(data)),
                "{:.0f}".format(sum(data)),
                "{:.0f}".format(min(data)),
                "{:.0f}".format(max(data)),
                "{:.0f}".format(stdev(data)),
                "{:.0f}".format(mean(data)),
                "{:.0f}".format(median(data)),
                "{:.0f}".format(N50(data)),
            ]
        )

    m = list(max(map(len, x)) + 2 for x in list(map(list, zip(*res))))
    m[0] -= 2
    s = "{:>{}}" * len(m)
    for x in res:
        c = x + m
        c[::2] = x
        c[1::2] = m
        print(s.format(*c), file=sys.stderr)


if __name__ == "__main__":
    main()
