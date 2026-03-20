---
name: shader-video
description: Create shader visualizations and send as videos. Trigger words - shader, glsl, visualization, fractal, procedural art, trippy video.
---

# Shader Video Skill

Generate GLSL shader visualizations and render them to video for iMessage/Signal delivery.

## Quick Start

```bash
# Render a shader to video (defaults: 4K, 6 seconds, high quality for iMessage)
~/.claude/skills/shader-video/scripts/render-shader shader.frag output.mov

# Fast preview (lower quality, smaller file)
~/.claude/skills/shader-video/scripts/render-shader shader.frag preview.mp4 --fast --width 720 --height 720

# Custom settings
~/.claude/skills/shader-video/scripts/render-shader shader.frag out.mov --duration 10 --width 1080 --height 1080
```

## How It Works

1. Write a GLSL fragment shader using standard uniforms (`u_resolution`, `u_time`)
2. The render script uses ModernGL (headless) to render frames
3. Frames are encoded to h265 video with ffmpeg
4. **For iMessage**: Use `.mov` extension for QuickTime container with proper branding

## iMessage Quality Settings

For best quality in iMessage, the script defaults to:
- **Resolution**: 4K (2160x2160)
- **Bitrate**: 50Mbps (matches iPhone camera)
- **Codec**: h265 with hvc1 tag
- **Container**: QuickTime (.mov) with `major_brand: qt`
- **Limit**: 100MB max

**CRITICAL**: Use `.mov` extension, not `.mp4`. iMessage handles QuickTime-branded videos better.

## Shader Format

Shaders should use these uniforms (glslViewer-compatible):

```glsl
#version 330
uniform vec2 u_resolution;  // Screen resolution in pixels
uniform float u_time;       // Time in seconds
out vec4 fragColor;         // Output color

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;
    // Your shader code here
    fragColor = vec4(uv, 0.5 + 0.5 * sin(u_time), 1.0);
}
```

## Creative Workflow: Recursive Self-Observation

The most interesting approach is **evolving shaders through visual feedback**:

1. Write initial shader with a concept
2. Render a single frame
3. Analyze the image - what works? what's missing?
4. Evolve the shader based on observations
5. Repeat until satisfied

This produces genuinely novel results because the shader evolves based on actual visual output rather than just code intuition.

## Inspiration Resources

### 1. Shadertoy (shadertoy.com)
The gold standard. Thousands of community shaders with full source code. Search by tags like "fractal", "raymarching", "voronoi", "procedural". Note: Shadertoy uses `iTime`, `iResolution`, `fragCoord` - translate to `u_time`, `u_resolution`, `gl_FragCoord`.

### 2. The Book of Shaders (thebookofshaders.com)
Patricio Gonzalez Vivo's interactive tutorial. Excellent for learning techniques: noise, fractals, patterns, shapes. Each chapter has editable examples.

### 3. Inigo Quilez's Articles (iquilezles.org)
The legendary shader artist. Deep dives on signed distance functions, smooth minimum, domain repetition, color palettes. His "useful functions" page is essential.

### 4. GLSL Sandbox (glslsandbox.com)
Another shader playground with different community. Good for finding weird experimental shaders that aren't on Shadertoy.

### 5. Shadergif (shadergif.com)
Shaders specifically designed for looping GIFs. Great for understanding how to create seamless animations.

### 6. Kishimisu's YouTube Channel
Excellent shader tutorial videos. "An introduction to Shader Art Coding" is a great starting point for understanding the mindset.

### 7. Art of Code YouTube Channel
Deep technical tutorials on raymarching, fractals, and procedural techniques. Very thorough explanations.

### 8. Bonzomatic / Shader Showdown Archives
Live coding shader competitions. Watch artists create shaders from scratch in real-time. Great for learning creative process and shortcuts.

### 9. twigl.app
Minimalist shader editor focused on code golf (ultra-short shaders). See how much can be done in 280 characters.

### 10. Shader Park (shaderpark.com)
JavaScript-based shader creation with a more accessible API. Good for understanding shader concepts before diving into raw GLSL.

### Reddit Communities (for ideas & research)
When researching new shader ideas or looking for creative inspiration:
- **r/creativecoding** - General creative coding, lots of shader posts
- **r/generative** - Generative art including shaders
- **r/shaders** - Dedicated shader sub (more game dev focused but still good)
- **r/proceduralgeneration** - Overlaps with shader techniques
- **r/twotriangles** - Specifically for shadertoy-style fragment shaders (name references fullscreen quad rendering)

### 11. Radiant Shaders (radiant-shaders.com)
Curated gallery of 80+ beautiful GLSL shaders, each inspired by a celebrity/artist. Organized by effect type with full source code. Great for studying specific techniques: flow fields, reaction-diffusion, raymarching, physics simulations, bioluminescence, volumetric lighting. Browse the full gallery at radiant-shaders.com/gallery/all — click any shader to see the GLSL source and a live preview.

### Other Communities
- **pouet.net** - Demoscene community where shader wizards hang out
- **fxhash.xyz** - NFT generative art platform with shader-heavy work
- **awesome-creative-coding GitHub** - Curated list with community links section

## Shader Techniques Reference

### Signed Distance Functions (SDF)
```glsl
float sdCircle(vec2 p, float r) {
    return length(p) - r;
}

float sdBox(vec2 p, vec2 b) {
    vec2 d = abs(p) - b;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}
```

### Domain Repetition
```glsl
vec2 repeat(vec2 p, float spacing) {
    return mod(p + spacing * 0.5, spacing) - spacing * 0.5;
}
```

### Smooth Minimum (organic blending)
```glsl
float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return mix(b, a, h) - k * h * (1.0 - h);
}
```

### Color Palette (Inigo Quilez)
```glsl
vec3 palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 1.0);
    vec3 d = vec3(0.0, 0.33, 0.67);
    return a + b * cos(6.28318 * (c * t + d));
}
```

### Voronoi
```glsl
float voronoi(vec2 p) {
    vec2 n = floor(p);
    vec2 f = fract(p);
    float minDist = 8.0;
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 neighbor = vec2(float(x), float(y));
            vec2 point = hash2(n + neighbor);
            float d = length(f - neighbor - point);
            minDist = min(minDist, d);
        }
    }
    return minDist;
}
```

### Fractal Brownian Motion (fbm)
```glsl
float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < 6; i++) {
        value += amplitude * noise(p);
        p *= 2.0;
        amplitude *= 0.5;
    }
    return value;
}
```

## Example Shaders

### Plasma
```glsl
void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;
    float t = u_time;
    float v = sin(uv.x * 10.0 + t) + sin(uv.y * 10.0 + t);
    v += sin((uv.x + uv.y) * 10.0 + t);
    v += sin(length(uv - 0.5) * 20.0 - t);
    fragColor = vec4(vec3(sin(v), sin(v + 2.094), sin(v + 4.188)) * 0.5 + 0.5, 1.0);
}
```

### Tunnel
```glsl
void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    float a = atan(uv.y, uv.x);
    float r = length(uv);
    float v = a / 3.14159 + u_time * 0.1;
    float w = 1.0 / r + u_time;
    fragColor = vec4(vec3(fract(v * 5.0), fract(w * 2.0), fract(v * w)), 1.0);
}
```

## Video Settings

For iMessage compatibility (defaults now optimized):
- **Resolution**: 2160x2160 (4K square) - matches iPhone camera
- **Duration**: 6 seconds default
- **FPS**: 30 is sufficient for most shaders
- **Codec**: h265 with `-tag:v hvc1` for iOS native playback
- **Bitrate**: 50Mbps with 60Mbps max (matches iPhone recording)
- **Container**: QuickTime (.mov) with `-brand qt` flag
- **Max size**: 100MB for iMessage

Use `--fast` flag for quick previews at lower quality.

## Output Directory Structure

**ALWAYS save shader projects to `~/Movies/shaders/`** with this structure:

```
~/Movies/shaders/
├── README.md                    # Index of all shader projects
├── project-name/                # kebab-case folder name
│   ├── shader-name.frag         # The GLSL source code
│   ├── shader-name.mov          # Rendered video (4K, QuickTime)
│   └── README.md                # Description of technique & parameters
└── another-project/
    ├── effect.frag
    ├── effect.mov
    └── README.md
```

Each project folder should contain:
1. **`.frag` file** - The GLSL fragment shader source
2. **`.mov` file** - Rendered video (use `.mov` for iMessage compatibility)
3. **`README.md`** - Brief description of the technique, inspiration source, and any tunable parameters

Example README.md for a shader project:
```markdown
# Murmurations

Boid flocking simulation inspired by r/generative.

## Technique
- Flow field from FBM noise for cohesive flock movement
- Multiple depth layers for parallax
- Dusk gradient background with vignette

## Parameters
- `numBirds` - Number of birds per layer (default: 80)
- `birdSize` - Size of bird chevrons (default: 0.015)
```

## Files

- `scripts/render-shader` - Main rendering CLI (ModernGL backend)
- `scripts/render-shader-metal` - Metal GPU renderer with GLSL→Metal transpiler (experimental)
- `scripts/depth-effects` - Image-based VJ effects using depth/masks
- `scripts/shader-template.frag` - Starting point for new shaders

## Performance Notes

**Render times** (M4 Pro, 4K 2160x2160, 6 seconds @ 30fps):
- Simple shaders (currents, plasma): ~45s total (15s render + 30s ffmpeg)
- Complex shaders (murmurations with 80 birds): ~8-10 minutes

**Metal vs ModernGL**: Both perform similarly because ModernGL on macOS already uses Metal via translation layer. The bottleneck is:
1. Shader complexity (nested loops, many samples)
2. ffmpeg h265 encoding (~30s for 4K)
3. PNG frame I/O

**Optimization tips**:
- Use `--fast` for previews (720p, lower bitrate)
- Reduce shader complexity (fewer loop iterations, simpler noise)
- For batch rendering, the Metal renderer could be extended to batch frames on GPU before readback

## Image-Based Effects (depth-effects)

Apply VJ-style effects to photos using depth maps and segmentation masks:

```bash
# Effects that only need image + depth:
depth-effects parallax photo.jpg depth.png output.mp4
depth-effects pan photo.jpg depth.png output.mp4
depth-effects rutt-etra photo.jpg depth.png output.mp4
depth-effects pixelsort photo.jpg depth.png output.mp4
depth-effects pointcloud photo.jpg depth.png output.mp4
depth-effects datamosh photo.jpg depth.png output.mp4

# Effects that also need a mask:
depth-effects hologram photo.jpg depth.png mask.png output.mp4
depth-effects particles photo.jpg depth.png mask.png output.mp4
depth-effects chromatic photo.jpg depth.png mask.png output.mp4

# Options:
depth-effects parallax img.jpg depth.png out.mp4 --duration 6 --fps 30
```

Available effects:
- **parallax** - TikTok-style 3D zoom (foreground in, background out)
- **pan** - Camera parallax pan with figure-8 motion
- **hologram** - Sci-fi hologram with scan lines (needs mask)
- **rutt-etra** - Classic 70s video synth scanlines
- **particles** - Person dissolves into drifting particles (needs mask)
- **chromatic** - RGB channels explode from edges (needs mask)
- **pixelsort** - Horizontal glitch streaks based on depth
- **pointcloud** - 3D point cloud with motion trails
- **datamosh** - Block displacement and color channel chaos

Generate depth/mask with vision skill:
```bash
~/.claude/skills/vision/scripts/estimate-depth photo.jpg photo
~/.claude/skills/vision/scripts/segment-person photo.jpg photo
# Creates: photo_depth_gray.png, photo_mask.png
```
