# Base-calling server parameters

The default settings for `Dorado` GPU should be sufficient for most use cases.

The one trick we sometimes use, on a _really_ high performance flow cell is to split the GPUs between `readfish` and `dorado`.

This of course assumes that you have a multiple GPU machine, such as PromethION tower.
In the new P24 towers, there are 4x NVIDIA A100 GPUs.

1. Stop dorado `sudo systemctl stop doradod`
1. View the available CUDA devices. `nvidia-smi`
1. Restart two dorado instances, splitting the devices between each.

Dorado:

```console
/opt/ont/dorado/bin/dorado_basecall_server --log_path /var/log/dorado --config dna_r10.4.1_e8.2_400bps_fast.cfg --ipc_threads 3 --port /tmp/.guppy/5555 --dorado_download_path /opt/ont/dorado-models --device cuda:0
```

```console
/opt/ont/dorado/bin/dorado_basecall_server --log_path /var/log/dorado --config dna_r10.4.1_e8.2_400bps_fast.cfg --ipc_threads 3 --port /tmp/.guppy/5556 --dorado_download_path /opt/ont/dorado-models --device cuda:1
```

1. Start readfish, base calling on port 5556
