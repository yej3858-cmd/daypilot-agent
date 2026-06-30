# DayPilot Agent

직장인의 업무 일정, 개인 일정, 마감 업무, 할 일, 컨디션을 입력받아 하루 우선순위와 실행 계획을 생성하는 Streamlit + LangChain 기반 AI 웹앱입니다.

## 파일 구조

```text
daypilot-agent/
├─ app.py
├─ requirements.txt
└─ README.md
```

## 주요 기능

- 한국어 Streamlit UI
- 오늘의 업무 일정, 개인 일정, 해야 할 업무, 마감 업무, 컨디션, 고민 입력
- LangChain `PromptTemplate` + Gemini `ChatGoogleGenerativeAI` 연결
- 아래 구조의 Markdown 결과 생성
  - 오늘의 핵심 요약
  - 우선순위 분류
  - 추천 실행 순서
  - 시간대별 하루 계획
  - 누락 방지 체크리스트
  - 업무 공유 문구
  - 오늘의 균형 조언
- 샘플 입력 불러오기
- Markdown 다운로드 버튼
- `Streamlit secrets` 기반 Gemini API 키 관리

## 로컬 실행 방법

### 1. 프로젝트 폴더 이동

```powershell
cd C:\Users\yej38\daypilot-agent
```

### 2. 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. 패키지 설치

```powershell
pip install -r requirements.txt
```

### 4. Streamlit secrets 설정

프로젝트 루트에 `.streamlit\secrets.toml` 파일을 만들고 아래처럼 작성합니다.

```toml
GOOGLE_API_KEY = "your-google-ai-studio-api-key"
```

또는 아래 키 이름도 지원합니다.

```toml
GEMINI_API_KEY = "your-google-ai-studio-api-key"
```

### 5. 앱 실행

```powershell
streamlit run app.py
```

## Streamlit Cloud 배포 방법

1. 이 폴더를 GitHub 저장소에 업로드합니다.
2. [Streamlit Community Cloud](https://share.streamlit.io/)에서 `New app`을 선택합니다.
3. 저장소와 브랜치를 고르고 Main file path에 `app.py`를 입력합니다.
4. 앱 설정의 `Secrets`에 아래 값 중 하나를 등록합니다.

```toml
GOOGLE_API_KEY = "your-google-ai-studio-api-key"
```

```toml
GEMINI_API_KEY = "your-google-ai-studio-api-key"
```

5. `Deploy`를 눌러 배포합니다.

## 구현 포인트

- Gemini API 키를 코드에 직접 작성하지 않고 `st.secrets["GOOGLE_API_KEY"]` 또는 `st.secrets["GEMINI_API_KEY"]`에서 읽습니다.
- 결과는 Markdown 문자열로 생성하고 화면 출력과 다운로드에 함께 사용합니다.
- 샘플 입력 버튼으로 초기 사용자가 빠르게 기능을 확인할 수 있습니다.

## 참고

- 기본 모델은 `gemini-2.5-flash`입니다.
- 필요하면 `app.py`에서 `model`, `temperature`를 조정할 수 있습니다.
