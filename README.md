# EntryMerge 2.0 Web

GitHub Pages에서 실행하는 EntryMerge 2.0 브라우저 버전입니다.

## 배포
1. 이 폴더 안의 모든 파일과 `icons` 폴더를 GitHub 저장소 최상위에 업로드합니다. (`manifest.json`과 앱 아이콘도 포함해야 합니다.)
2. GitHub 저장소의 **Settings → Pages**로 이동합니다.
3. **Deploy from a branch**를 선택하고 `main` / `/ (root)`를 지정한 뒤 저장합니다.
4. 생성된 `https://계정명.github.io/저장소명/` 주소로 접속합니다.

## 사용
- `.ent` 파일을 2개 이상 추가합니다.
- A 오브젝트 합치기 또는 B 장면 합치기를 선택합니다.
- 병합 버튼을 누르면 결과 `.ent` 파일이 다운로드됩니다.

## 기술
- 화면: HTML/CSS/JavaScript
- 병합 엔진: 원본 EntryMerge Python 병합 로직을 기반으로 브라우저용으로 조정
- 실행 환경: Pyodide (WebAssembly Python)
- ENT 파일은 브라우저 안에서 처리되며 별도 애플리케이션 서버로 업로드하지 않습니다.

첫 실행 시 Pyodide 런타임을 CDN에서 내려받으므로 인터넷 연결이 필요합니다.

## 검증 주의
샘플 ENT 파일을 실제 playentry.org에 업로드해 열어 보는 최종 호환성 검증은 별도로 필요합니다. 외부 확장 블록·하드웨어 전용 블록은 Entry 환경에 해당 기능이 있어야 할 수 있습니다.


## 웹앱 매니페스트
- `manifest.json`: 앱 이름, 실행 주소, 표시 방식, 색상 및 아이콘을 설정합니다.
- `icons/icon-192.png`, `icons/icon-512.png`: 웹앱 아이콘입니다.
- 매니페스트는 웹앱의 설치·표시 정보를 제공합니다. 브라우저의 실제 설치 가능 여부는 브라우저 정책과 서비스 워커 등 추가 조건에 따라 달라질 수 있습니다.
