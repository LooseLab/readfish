# Readfish analysis

👀

Woah what have we here? An _under development_ package to analyse readfish data? [Readfish Summarise](https://github.com/Adoni5/ReadfishSummarise). Please check this repo for up to date information about example output.

We have an inbuilt entry point in readfish to generate a summary of the data that you have collected, using this package.

> Please note that this is still under development, and the output is subject to change.
> Currently the only possible analysis is using the run FASTQ data, to recreate the decisions readfish would have made. Work is on going to add more analysis options.

## What is the purpose of this analysis module?

1. To provide a summary of the data that you have collected. By looking at the median read lengths, number of mapped reads, N50 per contig on each target, we can see how effectively readfish worked on the data.
1. FASTQ data can be demultiplexed into <condition.name>_<decision.name>.fastq.gz for further analysis with other tools.
1. ROUGH estimate of on target coverage.
1. Finally it is possible to recreate the decisions readfish made, and see how many reads would have been kept if you had used the same parameters.

## How to use
```console
usage: readfish stats [-h] [--log-level LOG-LEVEL] [--log-format LOG-FORMAT] [--log-file LOG-FILE] [--no-paf-out] [--no-demultiplex] [--no-csv] [--prom]
                      toml fastq_dir

positional arguments:
  toml                  TOML file used in the readfish experiment.
  fastq_dir             Path to the directory containing the FASTQ files produced by the readfish experiment

options:
  -h, --help            show this help message and exit
  --log-level LOG-LEVEL
                        One of: debug, info, warning, error or critical
  --log-format LOG-FORMAT
                        A standard Python logging format string (default: '%(asctime)s %(name)s %(message)s')
  --log-file LOG-FILE   A filename to write logs to, or None to write to the standard stream (default: None)
  --no-paf-out          Don't output the alignments in PAF format. By default PAF output Enabled.
  --no-demultiplex      Don't demultiplex and write out FASTQ. By default Multiplexing Enabled.
  --no-csv              Use this flag to not output CSV of the calculated summary stats. By default CSV output Enabled.
  --prom                Use this flag if the target platform was a PromethION
```

All outputs are opt out. By default, CSV of the summaries are written out, gzipped demultiplexed FATQ files are written out, and a PAF file of the alignments is written out.

An example command, with all outputs:

```bash
readfish stats --toml tests/static/stats_test/yeast_summary_test.toml --fastq-directory tests/static/stats_test/
```

``readfish stats``
*********************

.. automodule:: readfish.entry_points.stats



.. _a link:
