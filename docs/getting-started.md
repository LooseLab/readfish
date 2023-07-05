# Getting Started

Readfish is an adaptive sampling implementation for [ONT](https://nanoporetech.com) sequencers.
So to begin with you will need an ONT sequencer, currently we support the MinION Mk1B, GridION, and PromethION platforms.
As we use live base-calling and alignment the computer that is controlling the sequencer will also need to be capable of base-calling; ideally this would use a GPU.

We recommend for alignment that you pre-prepare a minimap2 index (`.mmi`) file. This can be done by using the `minimap -d` flag. An example command -

```bash
minimap2 -d <output_index>.mmi <input_reference>.fasta
```

Where `output_index` is the name of the index file to be output and `input_reference` is the name of the FASTA file that you want indexing.

This is then provided as the `fn_idx_in` value of the TOML file.

## Testing your computer

<!---
This is an aside, but we could have a 'readfish test-install' entry point.
This could be a complete series of test that starts with downloading a small bulk FAST5 file, setting up a simulation device and then starting/monitoring each test and eventually presenting the result.
-->

```{include} ../README.md
:start-after: <!-- begin-test -->
:end-before: <!-- end-test -->
```
