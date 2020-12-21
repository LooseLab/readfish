import argparse
import sys


try:
    import pandas as pd
    import numpy as np
except ImportError:
    sys.exit("pandas library is required, please install using 'pip install pandas'")


URL = (
    "https://ftp.ncbi.nlm.nih.gov/genomes/ASSEMBLY_REPORTS/assembly_summary_refseq.txt"
)


def main(parser, args):
    try:
        df = pd.read_csv(
            args.assembly_summary,
            sep="\t",
            skiprows=1,
            usecols=[
                "organism_name",
                "refseq_category",
                "species_taxid",
                "ftp_path",
            ],
        )
    except ValueError as e:
        sys.exit("Could not load assembly summary, we use: {}".format(URL))

    df[["genus", "species", "subspecies"]] = df["organism_name"].str.split(
        " ", n=2, expand=True
    )
    df["name"] = df["genus"].str.cat(df["species"], sep=" ")

    choices = [
        df["refseq_category"].eq("reference genome"),
        df["refseq_category"].eq("representative genome"),
        df["refseq_category"].eq("na"),
    ]
    df["priority"] = np.select(choices, [0, 1, 2], default=3)
    df = df.sort_values(["species_taxid", "priority"], ascending=True)

    df = df.drop_duplicates(subset="species_taxid", keep="first")
    df["fasta_path"] = df["ftp_path"].str.cat(
        df["ftp_path"].str.split("/").str[-1] + "_genomic.fna.gz",
        sep="/",
    )

    df.to_csv(
        args.output,
        sep="\t",
        index=False,
        columns=["species_taxid", "name", "fasta_path"],
        header=["taxid", "name", "fasta_path"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "assembly_summary",
        nargs="?",
        default=URL,
        help="Assembly summary from refseq, if not provided the latest one will be downloaded and used",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="refseq_urls.tsv",
        help="Output file name, default is 'refseq_urls.tsv'",
    )
    main(parser, parser.parse_args())
