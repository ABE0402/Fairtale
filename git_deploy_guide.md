# 🚀 AI Fairytale Studio - GitHub 배포 가이드

해당 프로젝트를 GitHub 브랜치(`feature/Automatic-fairytale`)에 올리기 위한 전체 명령어입니다.

## 1. 사용자 인증 설정 (최초 1회 필수)
커밋 오류(`Author identity unknown`)를 해결하기 위해 아래 명령어를 먼저 실행하세요.

```powershell
git config user.email "본인의이메일@example.com"
git config user.name "본인이름"
```

## 2. 원격 저장소 연결
이미 원격 저장소가 설정되어 있는지 확인하고 연결합니다.

```powershell
# 기존 원격지 삭제 (혹시 모를 충돌 방지)
git remote remove origin 

# 새 원격 저장소 연결
git remote add origin https://github.com/ABE0402/PLATFORMERS.git
```

## 3. 변경 사항 커밋 및 푸시
```powershell
# 모든 변경 파일 추가
git add .

# 커밋 (메시지 작성)
git commit -m "feat: AI Fairytale Studio automation with Vercel support"

# 원격 브랜치로 푸시
git push origin feature/Automatic-fairytale
```

## 4. 푸시 거절 시 대처법 (Troubleshooting)
푸시 도중 `[rejected]` 에러가 발생한다면, 원격 저장소와 로컬의 내용이 다르기 때문입니다.

### 방법 A: 강제 덮어쓰기 (추천)
로컬에 있는 내용이 최신이고, 원격의 내용을 무시해도 될 때 사용합니다.
```powershell
git push origin feature/Automatic-fairytale --force
```

### 방법 B: 원격 내용 가져와서 합치기
원격에 다른 사람이 올린 중요한 내용이 있을 때 사용합니다.
```powershell
git pull origin feature/Automatic-fairytale
```

---
**💡 팁**: 푸시할 때 GitHub 로그인 창이 뜨면 로그인해 주세요. 
성공적으로 완료되면 Vercel에서 해당 브랜치를 연결하여 배포를 마무리할 수 있습니다.
