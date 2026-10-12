# Authentication illustration assets

Created for the VieTech Admin/Staff sign-in page using the built-in `image_gen.imagegen` tool with transparent backgrounds. No CLI/API fallback was used.

- `vietech-logo.png`: 2172 × 724 RGBA PNG. Background extraction of the supplied VieTech logo reference. The last two conversation images were included; the prompt explicitly selected the logo and ignored the robot. The full red/blue mark, yellow star, and VieTech wordmark are present. Because the original attachment was not available as a local file, this is an image-tool extraction and may contain small differences from the source pixels.
- `waving-robot.png`: 1254 × 1254 RGBA PNG. Newly generated original white/silver/cyan robot waving in a sitting pose; no reference-image mechanism. Some faint white residue outside the silhouette can be visible on dark backgrounds. A cleanup attempt did not improve the result and was discarded.

## Final logo prompt

```text
Use case: background-extraction.
Asset type: exact existing VieTech system logo for a website header.
Input images: the first of the last two attached images is the EDIT TARGET: the complete red and blue VieTech mark and VieTech lettering on white. The second image is only an unrelated robot; ignore it completely.
Primary request: isolate the COMPLETE supplied VieTech logo on a genuinely transparent background. Remove ONLY the plain white background.
Constraints: preserve the exact existing red V, blue circuit T, yellow star, all internal details, original lettering "VieTech", capitalization, typography, gradients, outlines, original colors, spacing, and proportions. This is a careful background extraction, not a new logo. Keep both the left symbol and the entire right wordmark. Do not redesign, redraw, stylize, alter text, or combine it with the robot. Clean sharp antialiased edge and actual alpha transparency. No new elements or shadows. Fit the complete horizontal logo with a small transparent margin.
```

## Final robot prompt

```text
Use case: stylized-concept.
Asset type: transparent hero illustration for VieTech Admin and Staff login.
Primary request: create an original, polished, adorable friendly 3D robot waving hello with one raised hand and sitting comfortably, full body visible.
Scene/backdrop: genuinely transparent background, no backdrop, no checkerboard.
Subject: a compact white and silver robot with soft rounded shapes, a glossy black face screen, two luminous cyan eyes and a gentle cyan smiling mouth, small cyan-tipped antennae, round cyan-lit ear pods, a cyan chest light and dark navy joints. One hand raised in a readable friendly wave, with palm open and rounded fingers. Feet resting in front in a cute sitting pose. Original character design.
Style/medium: premium soft 3D studio render with refined ceramic and brushed metal material, appealing clean details and subtle cyan glow.
Composition/framing: three-quarter front view, centered, entire robot and raised hand contained in the image, generous small transparent margins, square canvas.
Lighting/mood: soft studio lighting, warm and welcoming, tasteful highlights.
Constraints: exactly one robot, no words, text, letters, brand logos, watermarks or background objects. Actual alpha transparency, no checkerboard pattern, avoid excessive cast shadow.
```

