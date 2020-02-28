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

We provide a JSON schema for validating configuration files:

```bash
ru_validate experiment_conf.toml ru_toml.schema.json
```

If you are providing targets using a text file the flag `-t` will attempt to 
check that these are compatible:

```bash
ru_validate -t experiment_conf.toml ru_toml.schema.json
```

Any errors with the configuration will be written to the terminal. 
