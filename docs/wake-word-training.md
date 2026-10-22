# Wake-word training data

This is a historical training record. The running processing service no longer uses the Edge Impulse model; it detects “Well actually” in finalized Azure Speech transcripts instead.

`scripts/generate_wake_word_dataset.py` creates an Edge Impulse-ready synthetic dataset for the exact phrase **“Well actually”** (without a pause after “Well”). It uses the Azure Speech resource in `rg_well_actually` and obtains the Speech key through the signed-in Azure CLI; no credentials are written to the repository.

The generator creates mono 16 kHz, 16-bit PCM WAV clips with a fixed 2-second window. Ten Azure Neural voices cover US, UK, Australian, and Indian English. Pitch and speaking rate are varied; the two Indian voices are held out from training and used only for testing. The `noise` class contains similar but non-target phrases plus low-level synthetic ambient noise. Each speech sample has a clean and a lightly noise-mixed copy. All data is synthetic; it is not a substitute for consented recordings from the target microphone and environment.

```sh
python3 scripts/generate_wake_word_dataset.py
```

Generated WAV files and their manifest are kept locally under the ignored `data/wake-word/` directory. In Edge Impulse Studio, use project **jimbobbennett-project-1** (project ID `1144536`) and upload the WAVs from each label/split directory with the matching label and category. The installed `edge-impulse-uploader` can do this, for example:

```sh
edge-impulse-uploader --label well-actually --category training data/wake-word/training/well-actually/*.wav
edge-impulse-uploader --label noise --category training data/wake-word/training/noise/*.wav
edge-impulse-uploader --label well-actually --category testing data/wake-word/testing/well-actually/*.wav
edge-impulse-uploader --label noise --category testing data/wake-word/testing/noise/*.wav
```

The trained impulse uses a 2-second time-series input at 16 kHz, an MFE audio DSP block, and a compact Keras classifier (32 dense units, dropout, then 16 dense units). Edge Impulse's transfer-learning keyword-spotting block currently requires a 1-second window, which would not contain this phrase at natural speaking rates; the 2-second classifier keeps the complete utterance intact.

The first run reached 100% on its 56-sample internal validation split and 75% on the 72-sample held-out test split. The test split uses two voices not seen during training, so the result highlights that this is a starting point, not a reliable detector. Before using it for the demo, capture consented examples with the eMeet M0 in the actual room and evaluate false accepts and misses; synthetic TTS alone is not representative enough for a reliable wake-word detector.

## Historical deployment

The previous implementation ran the trained model locally on the UNO Q. That runtime path has been removed; the processing service now detects the phrase from Azure Speech text and no longer requires, transfers, or loads the `.eim` file or Edge Impulse Linux SDK.
