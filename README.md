# MobiHoc 2026 Code

This repository contains the code used for the experiments in our MobiHoc 2026 paper.

Experiments are organized by dataset:

- `ACN-Data/`: experiments using the ACN-Data EV charging dataset.
- `EVCD-Data/`: experiments using the EVCD-Data EV charging dataset.

## Repository Structure

Each dataset directory contains:

- `Dataloader.py` — data loading and preprocessing
- `FCFS.py` — First-Come, First-Served baseline
- `MyAlg.py` — proposed online algorithm
- `OnlineAlgorithm.py` — base functionality for online algorithms
- `OptimalOffline.py` — offline optimal benchmark
- `ml_pipeline.ipynb` — machine-learning pipeline
- `my_experiments.ipynb` — experimental evaluation

## Datasets

The datasets themselves are not included in this repository.

### ACN-Data

Code for experiments conducted using the ACN-Data EV charging dataset is provided in `ACN-Data/`.

### EVCD-Data

Code for experiments conducted using the EVCD-Data EV charging dataset is provided in `EVCD-Data/`.

## Paper

This repository accompanies our MobiHoc 2026 paper.
