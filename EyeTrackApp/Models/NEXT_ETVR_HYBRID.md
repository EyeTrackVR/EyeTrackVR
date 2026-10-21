# NEXT Hybrid models

The full MobileNetV3 models come from the completed training run in
`LEAPv2_Training/E2E_ETVR_Hybrid`. ONNX files are copied unchanged from its
`onnx/` directory (ETVR/BSB exported 2026-10-18, PSVR exported 2026-10-19).

| Hardware selection | Training data under DATASET | Export stem |
|---|---|---|
| ETVR / ETVR Lite | `USER` | `NEXT_ETVR_HYBRID` |
| BSB / BSB Lite | `USER_BSB` | `NEXT_ETVR_HYBRID_BSB` |
| PSVR / PSVR Lite | `USER_TOBI` | `NEXT_ETVR_HYBRID_PSVR` |

Choose the model in Settings > Tracking Algorithm > Model. ETVR is the
default; Bigscreen setup mode automatically selects BSB until the user
manually chooses a model. Select PSVR or PSVR Lite manually. A manual
selection persists across setup-mode changes. Camera setup remains
independent of model choice: Bigscreen mode splits the shared side-by-side
camera into the left and right eye crops; standard mode uses separate eye
sources. Lite uses the matching fp16 export, with fp32 fallback if absent.

One shared ONNX session serves either camera or both. Input is raw RGB
float32 in 0..255, `[1, 6, 160, 160]`: left RGB followed by right RGB.
A missing or stale eye receives an all-zero black frame. The app resizes
and converts BGR to RGB; normalization is already inside the graph.

Output `[1, 12]` is left eyebrow/lid/squeeze, right eyebrow/lid/squeeze,
fused gaze X/Y, left monocular gaze X/Y, right monocular gaze X/Y. The
tracker consumes the first eight values; the graph routes fused gaze to
the present eye automatically. The same app gaze-Y conversion is used
for single-eye and dual-eye inference. Existing calibration, filtering
and user axis flips still apply. Recalibrate after changing model weights.
All six exports keep float32 I/O. Independent eyebrow inference uses its
existing model; PSVR and PSVR Lite fall back to the general ETVR eyebrow
model when that independent tracker is enabled.

## Precision sample

Across three paired captures per hardware family (dual-eye, left-only and
right-only inputs), maximum fp32/fp16 output differences were 0.0044 for
ETVR, 0.0077 for BSB and 0.0238 for PSVR. The PSVR maximum was on squeeze;
its maximum gaze difference was 0.0096. All source exports were copied
unchanged. CPU/DirectML checks passed for both precisions in all three modes.

## Export SHA-256

- `NEXT_ETVR_HYBRID.onnx`: `b453317b352fdddbb4aaaabb61a741701af0071335189d0feac9f6491e1c4b12`
- `NEXT_ETVR_HYBRID.fp16.onnx`: `47db1be15d981567db044bcf041d3569864a5283c35afca9c06651916ed9fd43`
- `NEXT_ETVR_HYBRID_BSB.onnx`: `bc56db847b69aaaf197b2458c2e2bf8643280d223de5e217d5d0b37d2a870d39`
- `NEXT_ETVR_HYBRID_BSB.fp16.onnx`: `65fed6238fc88dbba3ef3fb1fbc57c7beb84530593d4c154ab45177342ab2ad1`
- `NEXT_ETVR_HYBRID_PSVR.onnx`: `5dced7bbf4c3484b6de837371c7420b3e3c3041a2725ac6e49550f3032676f53`
- `NEXT_ETVR_HYBRID_PSVR.fp16.onnx`: `7d495027be541abdf6ba335eb0328c155b985f09d84893e6b24e322f692d7ade`
