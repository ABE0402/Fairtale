import os
import shutil
import base64
import zipfile
import json
import tempfile
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from PIL import Image, ImageChops

app = FastAPI(title="AI Fairytale Studio")

# 폴더 설정 (Vercel/Serverless 환경을 위해 /tmp 사용)
IS_VERCEL = "VERCEL" in os.environ
BASE_TMP_DIR = tempfile.gettempdir() if IS_VERCEL else os.getcwd()
UPLOAD_DIR = os.path.join(BASE_TMP_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_TMP_DIR, "output")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 프롬프트 템플릿 ────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """Create a colorful children's fairytale comic storybook illustration based on the fairy tale title provided by the user.

USER INPUT:
- Title: {title}
- English Level: {level}

The AI must automatically:
- generate the full story structure
- divide the story into 16 important scenes
- create narration text for each scene
- insert the narration text directly into the image
- keep consistent character designs across all panels
- adjust the English difficulty based on the selected English Level

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
- Keep the story flow clear and easy to follow.

If English Level is "Elementary School Upper Grades (4–6)":
- Use 2-4 longer, descriptive sentences per panel (15-25 words).
- Include rich dialogue, emotional expressions, and detailed character actions.
- Use advanced storytelling vocabulary (e.g., "pretended", "disappeared", "greedy").
- Allow for more complex grammatical structures.

STYLE:
Flat vector illustration style, clean and organized pastel color palette, 2D storybook art, simple and neat shapes, no heavy 3D shading, cute and expressive characters, warm and cozy atmosphere, clean outlines, minimalistic and highly readable composition, family-friendly children's book illustration.

LAYOUT:
- Multi-panel comic storybook layout
- Exactly 16 story panels
- Arrange the panels in a perfectly balanced 4x4 comic grid
- All 16 panels must have the same size and proportions
- Keep equal spacing between all panels
- Maintain consistent panel dimensions across the entire page
- Avoid oversized or undersized panels
- Avoid overlapping text between panels
- Keep all narration fully visible inside each panel
- Each panel must show one important moment from the story
- Add English narration text inside every panel
- Use large readable children's storybook font
- Use black outlined text for readability
- Cinematic storytelling composition
- Bright colorful fantasy backgrounds
- Cute facial expressions and dynamic character poses
- Keep visual pacing balanced from beginning to ending

STORY GENERATION RULES:
- Automatically create a simplified children's version of the story
- Maintain a clear beginning, middle, climax, and ending
- Carefully adapt the pacing of the story so that it spans exactly 16 panels, giving each panel a distinct action or moment.
- Focus on emotional and visually important scenes
- Each panel should contain different actions and environments
- The narration text should match the selected English Level
- Keep the story family-friendly and emotionally warm

VISUAL STYLE:
flat vector art, 2D children's book illustration, crisp and clean shapes, pastel tones, cozy atmosphere, adorable characters, simple flat shading, children's comic book illustration"""

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
    prompt = PROMPT_TEMPLATE.format(title=title, level=level)
    return {"prompt": prompt}

@app.post("/api/slice")
async def slice_comic(
    file: UploadFile = File(...), 
    mode: int = Query(1, description="1: 싱글, 2: 2장 펼침, 3: 3장 펼침")
):
    """스마트 크롭 + 1024px 고화질 업스케일 적용"""
    # Vercel 환경에서는 파일 시스템이 휘발성이므로 임시 경로 사용
    temp_filename = os.path.join(UPLOAD_DIR, file.filename)
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        raw_img = Image.open(temp_filename).convert("RGB")
        
        # 1. 외곽 하얀 여백 제거
        img = trim_white_margins(raw_img)
        img_width, img_height = img.size

        # 2. 4x4 분할 계산
        cols, rows = 4, 4
        cell_width = img_width / cols
        cell_height = img_height / rows

        # 출력 폴더 초기화 (임시 환경이므로 충돌 방지)
        if os.path.exists(OUTPUT_DIR):
            try: shutil.rmtree(OUTPUT_DIR)
            except: pass
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # 3. 정교하게 자르기 및 1024px 업스케일
        all_cells = []
        padding_w = cell_width * 0.01
        padding_h = cell_height * 0.01

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
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Fairytale Studio | AI 동화 제작 스튜디오</title>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700&family=Gowun+Dodum&family=Nanum+Myeongjo:wght@700&display=swap">
        <style>
            :root { 
                --primary: #FF85A1; 
                --secondary: #FFB3C6; 
                --accent: #FFC2D1; 
                --bg: #FFF5F7; 
                --text: #4A3036; 
                --card: #FFFFFF; 
                --border: #FFE4E9;
                --shadow: rgba(255, 133, 161, 0.15);
            }
            * { box-sizing: border-box; }
            body { 
                margin: 0; padding: 0; background-color: var(--bg); 
                font-family: 'Outfit', 'Gowun Dodum', sans-serif; 
                color: var(--text); line-height: 1.6;
            }
            .container { max-width: 1100px; margin: 0 auto; padding: 60px 20px; }
            
            /* Header */
            .header { text-align: center; margin-bottom: 60px; }
            .header h1 { 
                font-family: 'Nanum Myeongjo', serif; font-size: 3.5rem; 
                margin: 0; color: var(--primary); text-shadow: 2px 2px 0px white;
            }
            .header p { font-size: 1.1rem; color: #8A6B73; margin-top: 10px; }

            /* Workflow Steps */
            .steps { display: flex; flex-direction: column; gap: 40px; }
            .step-card { 
                background: var(--card); border-radius: 24px; padding: 40px;
                box-shadow: 0 10px 30px var(--shadow); border: 2px solid white;
            }
            .step-header { display: flex; align-items: center; gap: 15px; margin-bottom: 25px; }
            .step-num { 
                background: var(--primary); color: white; width: 35px; height: 35px; 
                border-radius: 50%; display: flex; align-items: center; justify-content: center;
                font-weight: bold; font-size: 1.2rem;
            }
            .step-title { font-size: 1.5rem; font-weight: bold; margin: 0; }

            /* Step 1: Prompt Builder */
            .input-group { margin-bottom: 20px; }
            .input-label { display: block; font-weight: bold; margin-bottom: 8px; font-size: 0.95rem; }
            input[type="text"], select { 
                width: 100%; padding: 15px; border-radius: 12px; border: 2px solid var(--border);
                font-size: 1rem; outline: none; transition: 0.2s;
            }
            input:focus, select:focus { border-color: var(--primary); box-shadow: 0 0 10px var(--shadow); }
            .level-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }
            .level-opt { 
                padding: 15px; border: 2px solid var(--border); border-radius: 12px;
                text-align: center; cursor: pointer; transition: 0.2s; font-weight: bold;
            }
            .level-opt.active { background: var(--primary); color: white; border-color: var(--primary); }
            .prompt-box { 
                background: #FDF1F3; border-radius: 12px; padding: 20px; 
                margin-top: 20px; position: relative; max-height: 200px; overflow-y: auto;
                font-family: 'Courier New', monospace; font-size: 0.85rem; border: 1px dashed var(--primary);
            }
            .btn-copy { 
                background: var(--primary); color: white; border: none; padding: 12px 25px;
                border-radius: 10px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 15px;
                transition: 0.3s;
            }
            .btn-copy:hover { transform: translateY(-2px); box-shadow: 0 5px 15px var(--shadow); }

            /* Step 2: Upload */
            .upload-area { 
                border: 3px dashed var(--border); border-radius: 20px; padding: 50px;
                text-align: center; cursor: pointer; transition: 0.3s;
            }
            .upload-area:hover { background: #FFF9FA; border-color: var(--primary); }
            .upload-icon { font-size: 3rem; margin-bottom: 10px; }

            /* Results */
            .mode-selector { display: flex; gap: 10px; margin-bottom: 25px; }
            .mode-btn { 
                padding: 10px 20px; border: 2px solid var(--border); border-radius: 30px;
                background: white; cursor: pointer; font-weight: bold; transition: 0.2s;
            }
            .mode-btn.active { background: var(--primary); color: white; border-color: var(--primary); }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 30px; }
            .page-card { 
                background: white; border-radius: 16px; overflow: hidden;
                box-shadow: 0 5px 15px rgba(0,0,0,0.05); border: 1px solid var(--border);
            }
            .page-card img { width: 100%; display: block; }
            .page-info { padding: 15px; text-align: center; font-weight: bold; color: var(--primary); }
            .btn-download { 
                background: var(--text); color: white; border: none; padding: 15px 30px;
                border-radius: 12px; font-weight: bold; cursor: pointer; 
            }

            /* Loading Overlay */
            #loading { 
                display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(255, 245, 247, 0.9); z-index: 1000;
                flex-direction: column; justify-content: center; align-items: center;
            }
            .spinner { 
                width: 60px; height: 60px; border: 6px solid var(--border);
                border-top-color: var(--primary); border-radius: 50%; animation: spin 1s linear infinite;
                margin-bottom: 20px;
            }
            @keyframes spin { to { transform: rotate(360deg); } }

            /* Toast */
            #toast {
                position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
                background: var(--text); color: white; padding: 12px 30px; border-radius: 30px;
                font-weight: bold; opacity: 0; transition: 0.5s; z-index: 2000;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header class="header">
                <h1>🪄 AI Fairytale Studio</h1>
                <p>상업적 퀄리티의 동화책을 가장 빠르고 선명하게 제작합니다</p>
            </header>

            <div class="steps">
                <!-- STEP 1 -->
                <div class="step-card">
                    <div class="step-header">
                        <div class="step-num">1</div>
                        <h2 class="step-title">스토리 및 프롬프트 생성</h2>
                    </div>
                    <div class="input-group">
                        <label class="input-label">동화 제목 (Title)</label>
                        <input type="text" id="titleInput" placeholder="예: 엄지공주의 모험 (Thumbelina's Adventure)" oninput="updatePrompt()">
                    </div>
                    <div class="input-group">
                        <label class="input-label">영어 난이도 (English Level)</label>
                        <div class="level-grid">
                            <div class="level-opt active" onclick="setLevel('Kindergarten', this)">유치원</div>
                            <div class="level-opt" onclick="setLevel('Elementary School Lower Grades (1–3)', this)">초등 저학년</div>
                            <div class="level-opt" onclick="setLevel('Elementary School Upper Grades (4–6)', this)">초등 고학년</div>
                        </div>
                    </div>
                    <div class="prompt-box" id="promptDisplay">프롬프트가 이곳에 생성됩니다...</div>
                    <button class="btn-copy" onclick="copyPrompt()">✨ 매직 프롬프트 복사하기</button>
                    <p style="font-size: 0.85rem; color: #8A6B73; text-align: center; margin-top: 15px;">
                        복사한 프롬프트를 <a href="https://chatgpt.com" target="_blank" style="color: var(--primary); font-weight: bold;">ChatGPT 웹사이트</a>에 붙여넣어 16칸 이미지를 생성하세요!
                    </p>
                </div>

                <!-- STEP 2 -->
                <div class="step-card">
                    <div class="step-header">
                        <div class="step-num">2</div>
                        <h2 class="step-title">이미지 업로드 및 고화질 분할</h2>
                    </div>
                    <div class="mode-selector">
                        <button class="mode-btn active" onclick="setMode(1, this)">📄 낱장 (16장)</button>
                        <button class="mode-btn" onclick="setMode(2, this)">📖 2장 펼침</button>
                        <button class="mode-btn" onclick="setMode(3, this)">📚 3장 펼침</button>
                    </div>
                    <div class="upload-area" onclick="document.getElementById('fileInput').click()">
                        <div class="upload-icon">🖼️</div>
                        <h3>생성된 16칸 이미지를 선택하세요</h3>
                        <p>자동으로 1024px 고화질 분할이 시작됩니다</p>
                        <input type="file" id="fileInput" style="display:none" accept="image/*" onchange="uploadImage(this)">
                    </div>
                </div>

                <!-- STEP 3: Results -->
                <div id="results-area" class="step-card" style="display:none">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:30px;">
                        <h2 class="step-title">✨ 변환 결과 (1024px HQ)</h2>
                        <button class="btn-download" onclick="location.href='/api/download-zip'">📦 전체 ZIP 다운로드</button>
                    </div>
                    <div id="image-grid" class="grid"></div>
                </div>
            </div>
        </div>

        <!-- Overlays -->
        <div id="loading">
            <div class="spinner"></div>
            <h2 id="loadingText">1024px 고화질로 업스케일링 중...</h2>
        </div>
        <div id="toast">복사되었습니다!</div>

        <script>
            let currentLevel = 'Kindergarten';
            let currentMode = 1;
            let currentPrompt = "";

            async function updatePrompt() {
                const titleInput = document.getElementById('titleInput');
                const title = titleInput.value.trim() || "[제목 입력]";
                
                try {
                    const res = await fetch('/api/build-prompt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title, level: currentLevel })
                    });
                    
                    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                    
                    const data = await res.json();
                    currentPrompt = data.prompt;
                    
                    const display = document.getElementById('promptDisplay');
                    display.innerText = currentPrompt;
                } catch (err) {
                    console.error("Failed to update prompt:", err);
                }
            }

            function setLevel(level, btn) {
                currentLevel = level;
                document.querySelectorAll('.level-opt').forEach(el => el.classList.remove('active'));
                btn.classList.add('active');
                updatePrompt();
            }

            function setMode(mode, btn) {
                currentMode = mode;
                document.querySelectorAll('.mode-btn').forEach(el => el.classList.remove('active'));
                btn.classList.add('active');
            }

            function copyPrompt() {
                const title = document.getElementById('titleInput').value.trim();
                if (!title) { alert("동화 제목을 먼저 입력해주세요!"); return; }
                
                if (!currentPrompt || currentPrompt.includes("[제목 입력]")) {
                    alert("프롬프트가 아직 생성되지 않았습니다.");
                    return;
                }
                
                navigator.clipboard.writeText(currentPrompt).then(() => {
                    showToast("프롬프트가 복사되었습니다!");
                }).catch(err => {
                    alert("복사 실패: " + err);
                });
            }

            function showToast(msg) {
                const t = document.getElementById('toast');
                t.innerText = msg;
                t.style.opacity = '1';
                setTimeout(() => t.style.opacity = '0', 2000);
            }

            async function uploadImage(input) {
                if (!input.files[0]) return;
                document.getElementById('loading').style.display = 'flex';
                const formData = new FormData();
                formData.append('file', input.files[0]);
                try {
                    const res = await fetch(`/api/slice?mode=${currentMode}`, { method: 'POST', body: formData });
                    if (!res.ok) throw new Error("서버 응답 오류");
                    const data = await res.json();
                    const grid = document.getElementById('image-grid');
                    grid.innerHTML = '';
                    data.images.forEach(img => {
                        grid.innerHTML += `
                            <div class="page-card">
                                <img src="${img.data}">
                                <div class="page-info">SCENE ${img.index}</div>
                            </div>
                        `;
                    });
                    document.getElementById('results-area').style.display = 'block';
                    document.getElementById('results-area').scrollIntoView({ behavior: 'smooth' });
                } catch (err) { alert('오류: ' + err.message); }
                finally { document.getElementById('loading').style.display = 'none'; input.value = ''; }
            }

            // Init
            window.onload = () => {
                updatePrompt();
            };
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
