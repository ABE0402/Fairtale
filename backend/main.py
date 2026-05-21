import os
import shutil
import base64
import zipfile
import json
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Body, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageChops, ImageEnhance, ImageDraw, ImageFont
import textwrap

app = FastAPI(title="AI Fairytale Studio")

# static 폴더 생성 및 마운트 (크레용스쿨 로고 등 정적 파일 지원)
base_dir = os.path.dirname(os.path.abspath(__file__))
parent_static = os.path.join(base_dir, "..", "static")
local_static = os.path.join(base_dir, "static")

if os.path.exists(parent_static):
    app.mount("/static", StaticFiles(directory=parent_static), name="static")
else:
    os.makedirs(os.path.join(local_static, "img"), exist_ok=True)
    app.mount("/static", StaticFiles(directory=local_static), name="static")

# 폴더 설정
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 프롬프트 템플릿 ────────────────────────────────────────────────────────────
SCRIPT_PROMPT_TITLE_TEMPLATE = """Create a children's fairytale story script based on the following:

- Title: {title}
- English Level: {level}

RULES:
- Automatically create a simplified children's version of the story.
- Maintain a clear beginning, middle, climax, and ending.
- Divide the story into EXACTLY 16 important scenes.
- The narration text should match the selected English Level.
- Keep the story family-friendly and emotionally warm.

ENGLISH LEVEL RULES:
If English Level is "Kindergarten":
- Limit narration to 1-2 very short sentences per panel (under 10 words).
- Heavily use fun sound words and onomatopoeia (e.g., "Chop, chop!", "Splash!", "Poof!").
- Use extremely simple, repetitive everyday vocabulary.
- Keep dialogues very short and repetitive (e.g., "No, no!", "Yes, yes!").

If English Level is "Elementary School Lower Grades (1–3)":
- Use 1-3 short, natural sentences per panel (10-15 words).
- Include simple dialogue mixed with basic narrative descriptions.
- Use beginner-level storytelling vocabulary.

If English Level is "Elementary School Upper Grades (4–6)":
- Use 2-4 longer, descriptive sentences per panel (15-25 words).
- Include rich dialogue, emotional expressions, and detailed character actions.
- Use advanced storytelling vocabulary (e.g., "pretended", "disappeared", "greedy").

OUTPUT FORMAT (JSON ONLY):
You MUST output the final 16 scenes as a JSON array of strings. Do not output anything else.
```json
[
  "Text for scene 1...",
  "Text for scene 2...",
  ...
  "Text for scene 16..."
]
```
"""

SCRIPT_PROMPT_STORY_TEMPLATE = """Create a children's fairytale story script by dividing the provided fairytale text into exactly 16 sequential scenes.

USER INPUT:
- Title: {title}
- Full Story Text: {full_story}
- English Level: {level}

RULES:
- STRICT RULE: You MUST use the provided "Full Story Text" as the source material.
- Analyze the full story, and divide the narrative flow into EXACTLY 16 sequential scenes.
- Maintain a clear beginning, middle, climax, and ending matching the original text.
- Adapt the English narration text of the 16 scenes to match the selected English Level, but keep the original plot and meaning intact.
- Keep the story family-friendly and emotionally warm.

ENGLISH LEVEL RULES:
If English Level is "Kindergarten":
- Limit narration to 1-2 very short sentences per panel (under 10 words).
- Heavily use fun sound words and onomatopoeia (e.g., "Chop, chop!", "Splash!", "Poof!").
- Use extremely simple, repetitive everyday vocabulary.
- Keep dialogues very short and repetitive (e.g., "No, no!", "Yes, yes!").

If English Level is "Elementary School Lower Grades (1–3)":
- Use 1-3 short, natural sentences per panel (10-15 words).
- Include simple dialogue mixed with basic narrative descriptions.
- Use beginner-level storytelling vocabulary.

If English Level is "Elementary School Upper Grades (4–6)":
- Use 2-4 longer, descriptive sentences per panel (15-25 words).
- Include rich dialogue, emotional expressions, and detailed character actions.
- Use advanced storytelling vocabulary (e.g., "pretended", "disappeared", "greedy").

OUTPUT FORMAT (JSON ONLY):
You MUST output the final 16 scenes as a JSON array of strings. Do not output anything else.
```json
[
  "Text for scene 1...",
  "Text for scene 2...",
  ...
  "Text for scene 16..."
]
```
"""

IMAGE_PROMPT_TITLE_TEMPLATE = """Create a children's fairytale storybook illustration based on the title: {title}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ZERO text, letters, numbers, captions, or speech bubbles anywhere in the image. The images MUST be 100% clean.
- Generate a single image with EXACTLY 16 panels arranged in a perfectly balanced 4x4 grid (4 rows, 4 columns).
- Do NOT draw 3x3 or irregular shapes. It MUST be a perfect 4x4 grid.
- All 16 panels must be exactly the same size and proportions, separated by thin white lines.
- Each panel must show one important moment from the story sequentially.
- Original character designs only — no copyrighted references (e.g., Disney, Pixar).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ART STYLE (CRITICAL 'DNA' OF THE IMAGE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Overall Vibe: Modern educational minimalist flat vector children's book illustration.
- Line Art & Outlines: STRICTLY NO outlines, NO line art, NO border lines, outline-free flat vector art. All visual elements must be defined purely by flat color shapes, not lines or borders.
- Shading & Texture: STRICTLY 100% flat solid colors. Absolutely NO textures, NO paper textures, NO felt textures, NO gradients, NO drop shadows, NO shading, NO glossy 3D highlights, NO cinematic lighting. Surfaces must be perfectly smooth and clean.
- Characters: Extremely simple minimalist vector characters. Cute facial expressions, simple dots for eyes, simple curved lines for mouths, soft pink oval flushed cheeks. Soft, rounded, simple anatomy. No outlines or borders around characters.
- Colors: Warm, harmonized pastel color palette (terracotta, soft greens, faded blues, warm wood tones). DO NOT use aggressively saturated neon colors. Clean solid color blocks.
- Backgrounds: Flat minimalist geometric shapes layered to create depth. Trees are simple solid blobs, clouds are simple solid scallops. Absolutely no realistic textures or outlined borders.
- STRICTLY BAN: NO outlines, NO line art, NO sketch lines, NO textures, NO paper/felt texture overlays, NO drop shadows, NO gradients, NO 3D rendering, NO Disney/Pixar style, NO photorealism, NO watercolor.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHARACTER DESIGN (keep consistent across ALL 16 panels)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Create specific, recognizable original character designs for the main characters of the story: {title}.
- Keep their clothing, hairstyles, colors, and facial features 100% consistent across all 16 panels.
- Ensure the character designs match the cultural setting of the story if applicable."""

IMAGE_PROMPT_STORY_TEMPLATE = """Create a children's fairytale storybook illustration based on the following story text:

STORY TEXT:
{full_story}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ZERO text, letters, numbers, captions, or speech bubbles anywhere in the image. The images MUST be 100% clean.
- Generate a single image with EXACTLY 16 panels arranged in a perfectly balanced 4x4 grid (4 rows, 4 columns).
- Do NOT draw 3x3 or irregular shapes. It MUST be a perfect 4x4 grid.
- All 16 panels must be exactly the same size and proportions, separated by thin white lines.
- Each panel must show one important moment from the story sequentially.
- Original character designs only — no copyrighted references (e.g., Disney, Pixar).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ART STYLE (CRITICAL 'DNA' OF THE IMAGE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Overall Vibe: Modern educational minimalist flat vector children's book illustration.
- Line Art & Outlines: STRICTLY NO outlines, NO line art, NO border lines, outline-free flat vector art. All visual elements must be defined purely by flat color shapes, not lines or borders.
- Shading & Texture: STRICTLY 100% flat solid colors. Absolutely NO textures, NO paper textures, NO felt textures, NO gradients, NO drop shadows, NO shading, NO glossy 3D highlights, NO cinematic lighting. Surfaces must be perfectly smooth and clean.
- Characters: Extremely simple minimalist vector characters. Cute facial expressions, simple dots for eyes, simple curved lines for mouths, soft pink oval flushed cheeks. Soft, rounded, simple anatomy. No outlines or borders around characters.
- Colors: Warm, harmonized pastel color palette (terracotta, soft greens, faded blues, warm wood tones). DO NOT use aggressively saturated neon colors. Clean solid color blocks.
- Backgrounds: Flat minimalist geometric shapes layered to create depth. Trees are simple solid blobs, clouds are simple solid scallops. Absolutely no realistic textures or outlined borders.
- STRICTLY BAN: NO outlines, NO line art, NO sketch lines, NO textures, NO paper/felt texture overlays, NO drop shadows, NO gradients, NO 3D rendering, NO Disney/Pixar style, NO photorealism, NO watercolor.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHARACTER DESIGN (keep consistent across ALL 16 panels)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Create specific, recognizable original character designs for the main characters of the story detailed in the STORY TEXT.
- Keep their clothing, hairstyles, colors, and facial features 100% consistent across all 16 panels.
- Ensure the character designs match the cultural setting of the story if applicable."""

# ── 이미지 처리 유틸리티 ────────────────────────────────────────────────────────
def trim_white_margins(img):
    """이미지 외곽의 하얀 여백을 자동으로 제거"""
    bg = Image.new(img.mode, img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

def merge_images(image_list):
    """여러 장의 이미지를 가로로 합침"""
    if not image_list: return None
    widths, heights = zip(*(i.size for i in image_list))
    total_width = sum(widths)
    max_height = max(heights)
    new_img = Image.new('RGB', (total_width, max_height), (255, 255, 255))
    x_offset = 0
    for img in image_list:
        new_img.paste(img, (x_offset, 0))
        x_offset += img.size[0]
    return new_img

# ── API 엔드포인트 ──────────────────────────────────────────────────────────────
@app.post("/api/build-prompt")
async def build_prompt(data: dict = Body(...)):
    title = data.get("title", "Unknown Title")
    level = data.get("level", "Kindergarten")
    full_story = data.get("full_story", "").strip()
    
    if full_story:
        script_prompt = SCRIPT_PROMPT_STORY_TEMPLATE.format(title=title, level=level, full_story=full_story)
        image_prompt = IMAGE_PROMPT_STORY_TEMPLATE.format(full_story=full_story)
    else:
        script_prompt = SCRIPT_PROMPT_TITLE_TEMPLATE.format(title=title, level=level)
        image_prompt = IMAGE_PROMPT_TITLE_TEMPLATE.format(title=title)
        
    return {"script_prompt": script_prompt, "image_prompt": image_prompt}

@app.post("/api/slice")
async def slice_comic(
    file: UploadFile = File(...), 
    story_script: str = Form(None),
    mode: int = Query(1, description="1: 싱글, 2: 2장 펼침, 3: 3장 펼침")
):
    """스마트 크롭 + 1024px 고화질 업스케일 적용"""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        raw_img = Image.open(file_path).convert("RGB")
        
        # 1. 외곽 하얀 여백 제거 (밝은 배경 오작동으로 인한 잘림을 방지하기 위해 원본을 그대로 사용)
        img = raw_img
        img_width, img_height = img.size

        # 2. 4x4 분할 계산
        cols, rows = 4, 4
        cell_width = img_width / cols
        cell_height = img_height / rows

        if os.path.exists(OUTPUT_DIR):
            shutil.rmtree(OUTPUT_DIR)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # 3. 정교하게 자르기 및 1024px 업스케일 (패딩을 0으로 설정하여 그림 유실 완벽 방지)
        all_cells = []
        padding_w = 0
        padding_h = 0

        for r in range(rows):
            for c in range(cols):
                left = c * cell_width + padding_w
                top = r * cell_height + padding_h
                right = (c + 1) * cell_width - padding_w
                bottom = (r + 1) * cell_height - padding_h
                
                cell = img.crop((left, top, right, bottom))
                
                # ✨ HQ Upscale (LANCZOS)
                cell = cell.resize((1024, 1024), Image.Resampling.LANCZOS)
                all_cells.append(cell)

        # 대본 JSON 저장
        if story_script:
            script_path = os.path.join(OUTPUT_DIR, "story_script.json")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(story_script)

        # 4. 레이아웃 모드 적용
        result_data = []
        for i in range(0, len(all_cells), mode):
            batch = all_cells[i : i + mode]
            merged = merge_images(batch) if mode > 1 else batch[0]
            
            idx = (i // mode) + 1
            filename = f"result_{idx:02d}.png"
            merged.save(os.path.join(OUTPUT_DIR, filename), "PNG")
            
            buffered = BytesIO()
            merged.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            result_data.append({
                "index": idx,
                "data": f"data:image/png;base64,{img_str}"
            })

        return {"images": result_data, "mode": mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-zip")
async def download_zip():
    zip_path = os.path.join(UPLOAD_DIR, "fairytale_results.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(OUTPUT_DIR):
            for f in files:
                zipf.write(os.path.join(root, f), f)
    return FileResponse(zip_path, media_type="application/zip", filename="fairytale_results.zip")

# ── 프론트엔드 (UI) ──────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="ko">

<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CrayonSchool AI Fairytale Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&family=Outfit:wght@600;800&display=swap"
    rel="stylesheet" />
  <style>
    :root {
      --bg-ivory: #FAF8ED;
      --bg-card: #FFFFFF;
      --primary: #FFC000;
      --secondary: #215E80;
      --accent: #4189B3;
      --text-black: #111111;
      --text-gray: #555555;
      --border: rgba(33, 94, 128, 0.1);
      --radius-md: 12px;
      --radius-lg: 16px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background: var(--bg-ivory);
      color: var(--text-black);
      font-family: 'Noto Sans KR', sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    /* --- HEADER --- */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.8rem 2rem;
      background: #fff;
      border-bottom: 1px solid var(--border);
    }

    .logo {
      height: 84px;
      object-fit: contain;
    }

    .header-info {
      font-size: 0.85rem;
      color: var(--text-gray);
      font-weight: 500;
    }

    /* --- MAIN LAYOUT --- */
    main {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 1.5rem;
      padding: 1.5rem;
      flex: 1;
      max-width: 1400px;
      margin: 0 auto;
      width: 100%;
    }

    .card {
      background: var(--bg-card);
      border-radius: var(--radius-lg);
      border: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      box-shadow: 0 4px 20px rgba(33, 94, 128, 0.03);
      padding: 1.5rem;
      gap: 1.5rem;
    }

    .section-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--secondary);
      margin-bottom: 0.8rem;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .required-dot {
      width: 5px;
      height: 5px;
      background: var(--primary);
      border-radius: 50%;
    }

    /* Category Grid (Tab Toggle) */
    .category-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .category-card {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 1rem;
      cursor: pointer;
      transition: 0.2s;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .category-card.active {
      border-color: var(--secondary);
      background: #f0f7fa;
    }

    .cat-icon {
      font-size: 1.2rem;
    }

    .cat-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--secondary);
    }

    /* Input text & Textarea */
    .title-input {
      width: 100%;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font-size: 0.85rem;
      outline: none;
      transition: border-color 0.2s;
    }

    .title-input:focus {
      border-color: var(--secondary);
    }

    .story-textarea {
      width: 100%;
      height: 120px;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font-size: 0.85rem;
      resize: none;
      outline: none;
      transition: border-color 0.2s;
    }

    .story-textarea:focus {
      border-color: var(--secondary);
    }

    /* English Level Selector (Grid) */
    .level-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 10px;
    }

    .level-card {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 0.8rem;
      text-align: center;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--text-gray);
      transition: 0.2s;
    }

    .level-card.active {
      background: var(--secondary);
      color: #fff;
      border-color: var(--secondary);
    }

    /* Prompt Box & Copy Buttons */
    .prompt-box {
      background: #fcfbf4;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 0.8rem;
      font-size: 0.75rem;
      color: var(--text-gray);
      height: 100px;
      overflow-y: auto;
      font-family: monospace;
      white-space: pre-wrap;
      word-break: break-all;
    }

    .prompt-container {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 15px;
    }

    .btn-copy {
      background: var(--secondary);
      color: #fff;
      border: none;
      padding: 0.6rem;
      border-radius: var(--radius-md);
      font-weight: 700;
      cursor: pointer;
      font-size: 0.8rem;
      margin-top: 5px;
      transition: 0.2s;
      width: 100%;
    }

    .btn-copy:hover {
      background: var(--accent);
    }

    /* Drop Zone */
    .drop-zone {
      border: 2px dashed rgba(33, 94, 128, 0.15);
      border-radius: var(--radius-md);
      padding: 1.5rem;
      text-align: center;
      background: var(--bg-ivory);
      cursor: pointer;
      position: relative;
      transition: 0.2s;
    }

    .drop-zone:hover {
      border-color: var(--secondary);
    }

    .drop-text-main {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--secondary);
      margin-bottom: 2px;
    }

    .drop-text-sub {
      font-size: 0.75rem;
      color: var(--text-gray);
    }

    /* JSON Input Area */
    .json-textarea {
      width: 100%;
      height: 90px;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font-size: 0.8rem;
      font-family: monospace;
      resize: none;
      outline: none;
    }

    /* --- RIGHT COLUMN: INFO & STATUS --- */
    .info-side {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .rules-box {
      background: #fcfbf4;
      border-radius: 10px;
      padding: 1rem;
      margin-bottom: 1rem;
    }

    .rules-list {
      list-style: none;
      font-size: 0.75rem;
      color: var(--text-gray);
      line-height: 1.8;
    }

    .rules-list li::before {
      content: '•';
      color: var(--primary);
      font-weight: bold;
      margin-right: 8px;
    }

    /* Progress Steps */
    .progress-steps {
      display: flex;
      flex-direction: column;
      gap: 0.8rem;
      margin-top: 10px;
    }

    .step {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 0.8rem;
      color: var(--text-gray);
    }

    .step-icon {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      border: 1px solid #ddd;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.7rem;
      flex-shrink: 0;
    }

    .step.active {
      color: var(--secondary);
      font-weight: 700;
    }

    .step.active .step-icon {
      border-color: var(--secondary);
      background: #eef6f9;
    }

    .step.done {
      color: #aaa;
    }

    .step.done .step-icon {
      background: #e8f5e9;
      border-color: #4caf50;
      color: #4caf50;
    }

    /* How It Works Step */
    .how-it-works {
      padding: 1.2rem;
    }

    .how-step {
      margin-bottom: 0.8rem;
      display: flex;
      gap: 10px;
    }

    .how-num {
      font-family: 'Outfit';
      color: var(--primary);
      font-weight: 800;
      font-size: 1.1rem;
    }

    .how-text-title {
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--secondary);
    }

    .how-text-desc {
      font-size: 0.75rem;
      color: var(--text-gray);
      line-height: 1.4;
    }

    /* Mode Selector Buttons */
    .mode-selector {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px;
    }

    .mode-btn {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 0.6rem;
      cursor: pointer;
      background: #fff;
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--secondary);
      transition: 0.2s;
      text-align: center;
    }

    .mode-btn.active {
      background: var(--secondary);
      color: #fff;
      border-color: var(--secondary);
    }

    /* --- RESULTS AREA --- */
    .results-container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 0 1.5rem 3rem 1.5rem;
      width: 100%;
    }

    .results-card {
      background: var(--bg-card);
      border-radius: var(--radius-lg);
      border: 1px solid var(--border);
      box-shadow: 0 4px 20px rgba(33, 94, 128, 0.03);
      padding: 2rem;
    }

    .results-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1rem;
    }

    .results-title {
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--secondary);
    }

    .btn-action-container {
      display: flex;
      gap: 10px;
    }

    .btn-action {
      background: var(--secondary);
      color: #fff;
      border: none;
      padding: 0.6rem 1.2rem;
      border-radius: var(--radius-md);
      font-weight: 700;
      cursor: pointer;
      font-size: 0.85rem;
      transition: 0.2s;
    }

    .btn-action:hover {
      background: var(--accent);
    }

    .btn-action-dark {
      background: #1E6B43;
      color: #fff;
      border: none;
      padding: 0.6rem 1.2rem;
      border-radius: var(--radius-md);
      font-weight: 700;
      cursor: pointer;
      font-size: 0.85rem;
      transition: 0.2s;
    }

    .btn-action-dark:hover {
      background: #154c30;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
      margin-top: 1.5rem;
    }

    .page-card {
      background: #fff;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      overflow: hidden;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.02);
      display: flex;
      flex-direction: column;
      transition: transform 0.2s;
    }

    .page-card:hover {
      transform: translateY(-3px);
    }

    /* Loading Overlay */
    #loading {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(250, 248, 237, 0.9);
      z-index: 1000;
      flex-direction: column;
      justify-content: center;
      align-items: center;
    }

    .spinner {
      width: 50px;
      height: 50px;
      border: 5px solid var(--border);
      border-top-color: var(--secondary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin-bottom: 20px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    /* Toast */
    #toast {
      position: fixed;
      bottom: 30px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--secondary);
      color: white;
      padding: 10px 25px;
      border-radius: 20px;
      font-weight: 700;
      font-size: 0.85rem;
      opacity: 0;
      transition: 0.5s;
      z-index: 2000;
      box-shadow: 0 4px 15px rgba(33, 94, 128, 0.2);
    }
  </style>
</head>

<body>

  <header>
    <img src="/static/img/크레용스쿨_로고(강좌정보출력물)-1.png" alt="CrayonSchool" class="logo">
    <div class="header-info">AI Fairytale Studio <span style="margin-left:10px; color:var(--accent)">v2.0 Premium</span></div>
  </header>

  <main>
    <section class="card input-side">
      <!-- 생성 방식 토글 -->
      <div>
        <div class="section-title"><span class="required-dot"></span>생성 방식 선택</div>
        <div class="category-grid">
          <div class="category-card active" id="tabTitleBtn" onclick="switchGenerationMode('title')">
            <span class="cat-icon">✏️</span>
            <div>
              <div class="cat-title">동화 제목으로 생성</div>
            </div>
          </div>
          <div class="category-card" id="tabStoryBtn" onclick="switchGenerationMode('story')">
            <span class="cat-icon">📝</span>
            <div>
              <div class="cat-title">완성된 동화로 생성</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 동화 제목 입력 -->
      <div>
        <div class="section-title"><span class="required-dot"></span>동화 제목 (Title)</div>
        <input type="text" class="title-input" id="titleInput" placeholder="예: 엄지공주의 모험 (Thumbelina's Adventure)" oninput="updatePrompt()">
      </div>

      <!-- 완성된 동화 텍스트 입력 (스토리 전용) -->
      <div id="storyInputGroup" style="display: none;">
        <div class="section-title"><span class="required-dot"></span>완성된 동화 텍스트 (Full Story Text)</div>
        <textarea class="story-textarea" id="fullStoryInput" placeholder="준비된 동화 텍스트 전체를 입력해 주세요. 입력된 내용을 정밀하게 분석하여 16장면 매직 프롬프트로 다듬어줍니다." oninput="updatePrompt()"></textarea>
      </div>

      <!-- 영어 난이도 -->
      <div>
        <div class="section-title"><span class="required-dot"></span>영어 난이도 (English Level)</div>
        <div class="level-grid">
          <div class="level-card active" id="level-k" onclick="setLevel('Kindergarten', this)">유치원</div>
          <div class="level-card" id="level-e-low" onclick="setLevel('Elementary School Lower Grades (1–3)', this)">초등 저학년</div>
          <div class="level-card" id="level-e-high" onclick="setLevel('Elementary School Upper Grades (4–6)', this)">초등 고학년</div>
        </div>
      </div>

      <!-- 프롬프트 출력 & 복사 컨테이너 -->
      <div>
        <div class="section-title">스튜디오 매직 프롬프트 빌더</div>
        <div class="prompt-container">
          <div>
            <div style="font-size:0.75rem; font-weight:700; color:var(--secondary); margin-bottom:5px;">📝 1. 대본 생성 프롬프트</div>
            <div class="prompt-box" id="scriptPromptDisplay">프롬프트를 로드하는 중...</div>
            <button class="btn-copy" onclick="copyScriptPrompt()">✨ 대본 프롬프트 복사</button>
          </div>
          <div>
            <div style="font-size:0.75rem; font-weight:700; color:var(--secondary); margin-bottom:5px;">🎨 2. 그림 생성 프롬프트</div>
            <div class="prompt-box" id="imagePromptDisplay">프롬프트를 로드하는 중...</div>
            <button class="btn-copy" onclick="copyImagePrompt()">✨ 그림 프롬프트 복사</button>
          </div>
        </div>
      </div>

      <!-- ChatGPT 안내 가이드 및 링크 -->
      <div style="background: #fcfbf4; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1rem; font-size: 0.8rem; line-height: 1.6; color: var(--text-gray);">
        <strong style="color: var(--secondary); font-weight: 700;">💡 사용 방법 & ChatGPT 바로가기:</strong>
        <ol style="margin-left: 1.2rem; margin-top: 5px; color: var(--text-gray);">
          <li>복사한 <strong>1. 대본 프롬프트</strong>를 <a href="https://chatgpt.com" target="_blank" style="color: var(--accent); font-weight: 700; text-decoration: underline;">ChatGPT 웹사이트 🚀</a>에 붙여넣어 <strong>16장면의 JSON 대본 텍스트</strong>를 얻으세요.</li>
          <li>복사한 <strong>2. 그림 프롬프트</strong>를 붙여넣어 글씨와 테두리가 없는 맑은 <strong>16칸(4x4) 일러스트 그리드 이미지</strong>를 생성하여 얻으세요.</li>
        </ol>
      </div>

      <!-- 스토리 대본 JSON 입력 -->
      <div>
        <div class="section-title">GPT 생성 스토리 텍스트 (JSON) <span style="font-size:0.7rem; font-weight:normal; color:var(--text-gray); margin-left:10px;">대본을 아래에 붙여넣으세요</span></div>
        <textarea class="json-textarea" id="jsonInput" placeholder='[\n  "Once upon a time...",\n  "..."\n]'></textarea>
      </div>

      <!-- 레이아웃 모드 및 파일 업로드 드롭존 -->
      <div>
        <div class="section-title"><span class="required-dot"></span>레이아웃 모드 및 업로드</div>
        <div style="display:flex; flex-direction:column; gap:12px;">
          <div class="mode-selector">
            <div class="mode-btn active" onclick="setMode(1, this)">📄 낱장 (16장)</div>
            <div class="mode-btn" onclick="setMode(2, this)">📖 2장 펼침</div>
            <div class="mode-btn" onclick="setMode(3, this)">📚 3장 펼침</div>
          </div>
          
          <div class="drop-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
            <input type="file" id="fileInput" hidden accept="image/*" onchange="uploadImage(this)">
            <div class="drop-icon">📂</div>
            <div class="drop-text-main" id="upload-name-display">생성된 16칸 이미지를 선택하거나 끌어다 놓으세요</div>
            <div class="drop-text-sub">자동으로 텍스트 합성 및 1024px HQ 분할이 적용됩니다</div>
          </div>
        </div>
      </div>
    </section>

    <section class="info-side">
      <div class="card">
        <div class="section-title">AI 동화 제작 가이드</div>
        <div class="rules-box">
          <ul class="rules-list">
            <li><strong>테두리 및 질감 없는 벡터 스타일</strong>: 테두리선(Outlines)과 종이/펠트 질감(Textures)이 원천 배제된 깔끔한 플랫 solid 컬러로 이미지를 자동 유도합니다.</li>
            <li><strong>4x4 만화 그리드 최적화</strong>: 16칸의 장면이 동일한 간격과 비율로 한 이미지에 균등 배열되어 그려져야 합니다.</li>
            <li><strong>글씨 없는 깨끗한 일러스트</strong>: DALL-E로 그림 생성 시 일체의 텍스트나 말풍선이 섞이지 않도록 차단합니다.</li>
            <li><strong>스마트 HQ 1024px 분할</strong>: 분할 시 흐려지지 않게 선명도 및 대비 강화를 적용해 맑은 색감을 표현합니다.</li>
          </ul>
        </div>

        <div class="section-title">분할 및 변환 상태</div>
        <div class="progress-steps" id="progress-section">
          <div class="step" id="step-1">
            <div class="step-icon">1</div>매직 프롬프트 실시간 빌드
          </div>
          <div class="step" id="step-2">
            <div class="step-icon">2</div>4x4 이미지 그리드 검출 및 외곽 하얀 여백 트리밍
          </div>
          <div class="step" id="step-3">
            <div class="step-icon">3</div>1024px LANCZOS 고화질 슬라이스 및 색감 보정
          </div>
        </div>
      </div>

      <div class="card how-it-works">
        <div class="section-title" style="margin-bottom:1rem">HOW IT WORKS</div>
        <div class="how-step">
          <div class="how-num">01</div>
          <div>
            <div class="how-text-title">스토리 앤 템플릿 빌드</div>
            <div class="how-text-desc">스토리 텍스트 또는 제목을 통해 난이도별 최적화된 프롬프트를 만듭니다.</div>
          </div>
        </div>
        <div class="how-step">
          <div class="how-num">02</div>
          <div>
            <div class="how-text-title">DALL-E 그림 생성</div>
            <div class="how-text-desc">그림 프롬프트를 사용하여 질감/테두리 없는 고품질 4x4 그리드 이미지를 얻습니다.</div>
          </div>
        </div>
        <div class="how-step">
          <div class="how-num">03</div>
          <div>
            <div class="how-text-title">16장 컷 분할 및 대본 병합</div>
            <div class="how-text-desc">이미지와 JSON 대본을 업로드해 자막이 입혀진 아름다운 독립형 동화책을 완성합니다.</div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <!-- 편집 결과 영역 -->
  <section class="results-container" id="results-area" style="display: none;">
    <div class="results-card">
      <div class="results-header">
        <div class="results-title">✨ AI 동화 편집기 (1024px HQ)</div>
        <div class="btn-action-container">
          <button class="btn-action" onclick="downloadScript()">📝 수정된 대본 저장</button>
          <button class="btn-action-dark" onclick="location.href='/api/download-zip'">📦 이미지 ZIP 다운로드</button>
        </div>
      </div>
      <p style="font-size:0.8rem; color:var(--text-gray); margin-bottom:1rem; text-align:center;">
        각 장면의 대본 텍스트를 직접 수정할 수 있습니다. 수정을 완료한 후 <strong>[수정된 대본 저장]</strong> 버튼을 누르면 JSON 파일로 내보내집니다.
      </p>
      <div id="image-grid" class="grid"></div>
    </div>
  </section>

  <!-- 로딩 오버레이 -->
  <div id="loading">
    <div class="spinner"></div>
    <h2 id="loadingText" style="font-size:1.1rem; color:var(--secondary); font-weight:700;">1024px 고화질로 변환 및 분할하는 중...</h2>
  </div>

  <!-- 토스트 메시지 -->
  <div id="toast">복사되었습니다!</div>

  <script>
    let currentLevel = 'Kindergarten';
    let currentMode = 1;
    let currentScriptPrompt = "";
    let currentImagePrompt = "";
    let generationMode = 'title'; // 'title' or 'story'
    let panelTexts = [];

    function switchGenerationMode(mode) {
      generationMode = mode;
      document.getElementById('tabTitleBtn').classList.toggle('active', mode === 'title');
      document.getElementById('tabStoryBtn').classList.toggle('active', mode === 'story');
      
      const storyGroup = document.getElementById('storyInputGroup');
      if (mode === 'story') {
        storyGroup.style.display = 'block';
      } else {
        storyGroup.style.display = 'none';
        document.getElementById('fullStoryInput').value = '';
      }
      updatePrompt();
    }

    async function updatePrompt() {
      const titleInput = document.getElementById('titleInput');
      const title = titleInput.value.trim() || "[제목 입력]";
      
      const fullStoryInput = document.getElementById('fullStoryInput');
      const fullStory = generationMode === 'story' ? fullStoryInput.value.trim() : "";
      
      try {
        const res = await fetch('/api/build-prompt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, level: currentLevel, full_story: fullStory })
        });
        
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        
        const data = await res.json();
        currentScriptPrompt = data.script_prompt;
        currentImagePrompt = data.image_prompt;
        
        document.getElementById('scriptPromptDisplay').innerText = currentScriptPrompt;
        document.getElementById('imagePromptDisplay').innerText = currentImagePrompt;
      } catch (err) {
        console.error("Failed to update prompt:", err);
      }
    }

    function setLevel(level, btn) {
      currentLevel = level;
      document.querySelectorAll('.level-card').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
      updatePrompt();
    }

    function setMode(mode, btn) {
      currentMode = mode;
      document.querySelectorAll('.mode-btn').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
    }

    function copyScriptPrompt() {
      const title = document.getElementById('titleInput').value.trim();
      const story = document.getElementById('fullStoryInput').value.trim();
      if (generationMode === 'title' && !title) { alert("동화 제목을 먼저 입력해주세요!"); return; }
      if (generationMode === 'story' && !story) { alert("완성된 동화 텍스트를 먼저 입력해주세요!"); return; }
      if (!currentScriptPrompt) return;
      
      navigator.clipboard.writeText(currentScriptPrompt).then(() => {
        showToast("대본 프롬프트가 복사되었습니다!");
      }).catch(err => alert("복사 실패: " + err));
    }

    function copyImagePrompt() {
      const title = document.getElementById('titleInput').value.trim();
      const story = document.getElementById('fullStoryInput').value.trim();
      if (generationMode === 'title' && !title) { alert("동화 제목을 먼저 입력해주세요!"); return; }
      if (generationMode === 'story' && !story) { alert("완성된 동화 텍스트를 먼저 입력해주세요!"); return; }
      if (!currentImagePrompt) return;
      
      navigator.clipboard.writeText(currentImagePrompt).then(() => {
        showToast("그림 프롬프트가 복사되었습니다!");
      }).catch(err => alert("그림 프롬프트가 복사되었습니다!"));
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.style.opacity = '1';
      setTimeout(() => t.style.opacity = '0', 2000);
    }

    async function uploadImage(input) {
      if (!input.files[0]) return;
      
      const jsonText = document.getElementById('jsonInput').value.trim();
      let scriptData = [];
      if (jsonText) {
        try { scriptData = JSON.parse(jsonText); } catch(e) {}
      }

      document.getElementById('loading').style.display = 'flex';
      document.getElementById('loadingText').innerText = "4x4 동화 이미지를 분할하고 정밀 크롭하는 중...";

      // 가짜 변환 프로세스 시뮬레이션
      for (let i = 1; i <= 3; i++) {
        document.getElementById(`step-${i}`).className = 'step active';
      }

      const formData = new FormData();
      formData.append('file', input.files[0]);
      if (jsonText) formData.append('story_script', jsonText);

      try {
        const res = await fetch(`/api/slice?mode=${currentMode}`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error("서버 응답 오류");
        const data = await res.json();
        const grid = document.getElementById('image-grid');
        grid.innerHTML = '';
        panelTexts = [];

        data.images.forEach((img, i) => {
          const text = scriptData[i] || '';
          panelTexts.push(text);

          const card = document.createElement('div');
          card.className = 'page-card';
          card.innerHTML = `
              <div style="position:relative;">
                  <img src="${img.data}" style="width:100%; display:block;">
                  <div style="position:absolute; top:10px; left:10px; background:rgba(33, 94, 128, 0.85); color:#fff; font-size:0.75rem; font-weight:700; padding:4px 10px; border-radius:20px;">SCENE ${img.index}</div>
              </div>
              <div style="padding:14px; background:#fff; flex:1; display:flex; flex-direction:column; gap:8px;">
                  <label style="font-size:0.75rem; font-weight:700; color:var(--secondary); display:block;">📝 대본 텍스트</label>
                  <textarea id="panel-text-${i}" rows="3" oninput="panelTexts[${i}]=this.value" style="width:100%; resize:vertical; border-radius:8px; border:1px solid var(--border); padding:8px; font-size:0.8rem; font-family:inherit; line-height:1.5; outline:none; transition:border-color 0.2s;" onfocus="this.style.borderColor='var(--secondary)'" onblur="this.style.borderColor='var(--border)'">${text}</textarea>
              </div>
          `;
          grid.appendChild(card);
        });

        // 진행 프로세스 완료 표시
        for (let i = 1; i <= 3; i++) {
          document.getElementById(`step-${i}`).className = 'step done';
        }

        document.getElementById('results-area').style.display = 'block';
        document.getElementById('results-area').scrollIntoView({ behavior: 'smooth' });
        
        document.getElementById('upload-name-display').textContent = `${input.files[0].name} 업로드 및 분할 완료`;
      } catch (err) { 
        alert('오류: ' + err.message); 
      } finally { 
        document.getElementById('loading').style.display = 'none'; 
        input.value = ''; 
      }
    }

    function downloadScript() {
      document.querySelectorAll('[id^="panel-text-"]').forEach((el, i) => {
        panelTexts[i] = el.value;
      });
      const json = JSON.stringify(panelTexts, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'story_script_edited.json';
      a.click();
      URL.revokeObjectURL(url);
      showToast('수정된 대본이 저장되었습니다!');
    }

    // Drag and Drop event binding
    const dropZone = document.getElementById('dropZone');
    
    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.style.borderColor = 'var(--secondary)';
        dropZone.style.background = '#f0f7fa';
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.style.borderColor = 'rgba(33, 94, 128, 0.15)';
        dropZone.style.background = 'var(--bg-ivory)';
      }, false);
    });

    dropZone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files.length > 0) {
        const fileInput = document.getElementById('fileInput');
        fileInput.files = files;
        uploadImage(fileInput);
      }
    }, false);

    // Init
    window.onload = () => {
      updatePrompt();
    };
  </script>
</body>

</html>"""

# ── 구동 스크립트 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
