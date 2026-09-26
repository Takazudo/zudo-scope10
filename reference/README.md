# Source availability and rights

`catalog/sources.json` records current primary-source URLs and the nature of each review. Some PDFs were read through the web tool but could not be downloaded as bytes. The binary-fetch script is provided for local completion; it checks magic bytes and records hashes, but does not mark downloaded content electrically reviewed.

`assets/` contains existing manufacturer/supplier files recovered from the user's earlier component catalogue ZIP. Their records retain the original URLs and SHA-256 values. These third-party source assets are not licensed under the license for the newly written project code. Keep them for local engineering reference; review their respective terms before publishing download mirrors.

The ALPS STEP is original manufacturer geometry. No exact Waveshare/Pico or NKK STEP is included. The separately generated nominal envelopes are clearly different artifacts and do not replace missing exact CAD.
