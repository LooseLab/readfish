Read Until Configuration Files
===

Specification for the TOML files used to drive read until experiments.

---

Table of Contents
===
 - [TOML files](#toml-files)
 - [Config sections](#config-sections)
   - [Guppy connection](#guppy-connection)
   - [Conditions](#conditions)
 - [Validating a TOML](#validating-a-toml)
 
 
TOML files
===
Read Until experiments are configured using TOML files, which are minimal and 
easy-to-read markup files. Each line is either a key-value pair or a 'table' 
heading. See more in the [TOML specification](https://github.com/toml-lang/toml).


Config sections
===

Guppy connection
---
The `caller_settings` table specifies the basecalling parameters used by guppy.  

The `config_name` parameter must a valid guppy configuration excluding the file 
extension; these can be found in the `data` folder of the your guppy installation 
directory (`/opt/ont/guppy/data/*.cfg`).  

### Remote basecalling

```toml
[caller_settings]
config_name = "dna_r9.4.1_450bps_fast"
host = "REMOTE_SERVER_IP_ADDRESS"
port = "REMOTE_GUPPY_SERVER_PORT"
``` 

### Local basecalling

```toml
[caller_settings]
config_name = "dna_r9.4.1_450bps_fast"
host = "127.0.0.1"
port = 5555
```

Conditions
---
The `conditions` table holds the location of your minimap2 reference file and 
sets out the experimental conditions across the flowcell. The allowed keys are:

|          Key |       Type      | Values | Description |
|-------------:|:---------------:|:------:|:------------|
| reference | string | N/A | Required the absolute path for a minimap2 index |
| maintain_order | bool| N/A | (Optional) If `true` condition regions are ordered by their sequential numbering in the TOML file|
| axis | int | [0, 1] | (Optional) The axis that the flowcell is divided on. 0 is rows (left -> right), 1 is columns (top -> bottom); default is 1|


```toml
[conditions]
reference = "/absolute/path/to/reference.mmi"
```

Further, the table has sub-tables that determine the experimental conditions 
to apply to the flowcell, these should be sequentially numbered like so:

```toml
[conditions.0]
# ...

[conditions.1]
# ...
```

Each conditions sub-table must contain all of the following keys:

|          Key |       Type      | Values | Description |
|-------------:|:---------------:|:------:|:------------|
|name|string|N/A|The name given to this condition|
|control|bool|N/A|Is this a control condition. If `true` all reads will be ignored in this region|
|min_chunks|int|N/A|The minimum number of read chunks to evaluate|
|max_chunks|int|N/A|The maximum number of read chunks to evaluate|
|targets|string or array|N/A|The genomic targets to accept or reject; see [types](#target-types) and [formats](#target-formats)|
|single_on|string|[unblock, stop_receiving, proceed]|The action to take when a read has a single on-target mapping|
|multi_on|string|[unblock, stop_receiving, proceed]|The action to take when a read has multiple on-target mappings|
|single_off|string|[unblock, stop_receiving, proceed]|The action to take when a read has a single off-target mapping|
|multi_off|string|[unblock, stop_receiving, proceed]|The action to take when a read has multiple off-target mappings|
|no_seq|string|[unblock, stop_receiving, proceed]|The action to take when a read does not basecall|
|no_map|string|[unblock, stop_receiving, proceed]|The action to take when a read does not map to your reference|

The physical layout of each flowcell constrains how many experimental conditions 
can be used; the number of sub-tables in the `conditions` section determines how 
the flowcell is divided. 

The maximum number of conditions for MinION and PromethION flowcells is given in 
the table below. The number of conditions must be a factor of the number for the
selected combination.

<table>
  <tr>
    <td rowspan="2"></td>
    <th colspan="2">Axis</th>
  </tr>
  <tr>
    <th>0</th>
    <th>1</th>
  </tr>
  <tr>
    <th>MinION</th>
    <td>16</td>
    <td>32</td>
  </tr>
  <tr>
    <th>PromethION</th>
    <td>25</td>
    <td>120</td>
  </tr>
</table>

### Target Types

The targets parameter can accept either a string or an array of strings. If a
string is provided this should be a fully qualified path to a text file which 
consists of genomic targets in the [formats outlined below](#target-formats). 
When an array is given all the elements in the array must conform with the 
[formats below](#target-formats).

### Target Formats

When specifying the genomic targets to consider in a Read Until experiment we 
currently accept two formats `chromosome` or `coordinates`. 

EG `chromosome`: 
 - `>chr1 Human chromosome 1` becomes `chr1`
 
Targets given in this format specify the entire contig as a target to select for 
or against.
 
Alternatively, for `coordinates` the format `contig,start,stop,strand` is used:
 - `chr1,10,20,+`
 
Targets given in this format will only select (for or against) reads where the 
alignment start position is within the region on the given strand. 

Validating a TOML
===

We provide a [JSON schema](ru/static/ru_toml.schema.json) for validating 
configuration files:

```bash
ru_validate experiment_conf.toml
```

Any errors with the configuration will be written to the terminal. 

As an example - if the reference is missing you will see:

```text
ru_validate examples/human_chr_selection.toml
😻 Looking good!
Generating experiment description - please be patient!
This experiment has 1 region on the flowcell

No reference file provided

Region 'select_chr_21_22' (control=False) has 3 targets. Reads will be
unblocked when classed as single_off or multi_off; sequenced when
classed as single_on or multi_on; and polled for more data when
classed as no_map or no_seq.
```

The experiment report will tell you if targets are not represented in the reference (this is not a coordinate check, but is a chromosome name check):
```text
ru_validate examples/human_chr_selection.toml
😻 Looking good!
Generating experiment description - please be patient!
This experiment has 1 region on the flowcell

Using reference: /path/to/reference.mmi

Region 'select_chr_21_22' (control=False) has 3 targets of which 2 are
in the reference. Reads will be unblocked when classed as single_off
or multi_off; sequenced when classed as single_on or multi_on; and
polled for more data when classed as no_map or no_seq.

```

If the toml fails validation (i.e fields are missing or have non permitted values) you will see the following - note the problem field is reported on the second line. 

```text
ru_validate examples/human_chr_selection.toml
😾 this TOML file has failed validation. See below for details:
'min_chunks' is a required property

Failed validating 'required' in schema['properties']['conditions']['patternProperties']['^[0-9]+$']:
    {'additionalProperties': False,
     'properties': {'control': {'type': 'boolean'},
                    'max_chunks': {'minimum': 1, 'type': 'number'},
                    'min_chunks': {'minimum': 0, 'type': 'number'},
                    'multi_off': {'$ref': '#/definitions/modes',
                                  'type': 'string'},
                    'multi_on': {'$ref': '#/definitions/modes',
                                 'type': 'string'},
                    'name': {'minLength': 1, 'type': 'string'},
                    'no_map': {'$ref': '#/definitions/modes',
                               'type': 'string'},
                    'no_seq': {'$ref': '#/definitions/modes',
                               'type': 'string'},
                    'single_off': {'$ref': '#/definitions/modes',
                                   'type': 'string'},
                    'single_on': {'$ref': '#/definitions/modes',
                                  'type': 'string'},
                    'targets': {'items': {'oneOf': [{'pattern': '^[^,]+$'},
                                                    {'pattern': '^.+,[0-9]+,[0-9]+,[+-]$'}],
                                          'type': 'string'},
                                'type': ['array', 'string']}},
     'required': ['name',
                  'max_chunks',
                  'min_chunks',
                  'targets',
                  'single_on',
                  'single_off',
                  'multi_on',
                  'multi_off',
                  'no_seq',
                  'no_map',
                  'control'],
     'type': 'object'}

On instance['conditions']['0']:
    {'control': False,
     'max_chunks': inf,
     'multi_off': 'unblock',
     'multi_on': 'stop_receiving',
     'name': 'select_chr_21_22',
     'no_map': 'proceed',
     'no_seq': 'proceed',
     'single_off': 'unblock',
     'single_on': 'stop_receiving',
     'targets': ['chr21', 'chr22']}
```