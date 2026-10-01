# 태윤·도윤 스토리보드 영상 만들기

간단한 로컬 HTML 인터페이스입니다. 여러 시작 사진과 **외부에서 준비한 MiniMax H3 프롬프트**를 한 번에 넣고 `모두 영상 만들기`를 누릅니다. 완성 클립이 순서대로 모이면 ChatGPT 편집 지시를 입력하고 MP4를 내보냅니다. 기존 수동 타임라인은 `/advanced`에 있습니다.

## 실행

Python 3, FFmpeg, FFprobe가 필요합니다.

```bash
bash run.sh
```

브라우저에서 `http://127.0.0.1:18792`를 엽니다. `run.sh`는 서버가 종료되면 대기 후 다시 시작합니다. `TD_EDITOR_PORT`로 포트를 바꿀 수 있습니다.

1. `API 키 설정`에서 MiniMax API 키를 입력합니다. ChatGPT 편집까지 하려면 OpenAI API 키도 입력합니다. **ChatGPT 웹 구독과 OpenAI API 키는 별개입니다.** 키는 브라우저 실행 메모리와 해당 요청에만 사용되며 디스크·프로젝트 파일·GitHub에 저장하지 않습니다.
2. JPG·PNG·WEBP 시작 사진을 여러 장 선택하고 같은 개수의 H3 프롬프트를 붙여넣습니다. 여러 줄짜리 프롬프트 사이에는 단독 행 `---`를 넣고, 한 줄짜리 프롬프트라면 한 줄에 하나씩 넣습니다. 사진은 **파일명 숫자 순서**로 정렬되어 프롬프트와 1:1로 연결됩니다. 개수가 다르면 API 요청을 보내지 않습니다.
3. `모두 영상 만들기`가 각 장면을 차례로 MiniMax 공식 `MiniMax-H3` API에 제출하고, 완료 여부를 자동 확인합니다. 개별 장면 카드에서 수정·재시도할 수도 있습니다. 작업 ID는 브라우저 세션에 보존하므로 새로고침 후 키를 다시 입력하고 `상태 다시 확인`을 누를 수 있습니다.
4. 완성 클립이 순서대로 표시됩니다. 기존 MP4도 추가할 수 있습니다.
5. ChatGPT 편집 지시를 입력하면 대표 프레임과 생성 프롬프트를 바탕으로 클립 순서, 앞뒤 자르기, 원본 음소거 구간을 제안합니다. 화면에서 편집안을 확인한 뒤 MP4를 내보냅니다. ChatGPT는 이 경로에서 클립의 **음성을 듣지 않습니다.** 특정 대사를 제거하려면 시간을 지정하세요. 수동 음성 교체·Qwen3 TTS는 `/advanced`에서 이용할 수 있습니다.

MiniMax H3 영상 생성은 유료 API 호출입니다. `MiniMax-H3`의 사진 시작 프레임은 공식 `POST /v2/video_generation`의 `content` 배열에 `role=first_frame`으로 전송하며, 공식 `GET /v2/query/video_generation/{task_id}`로 결과를 조회합니다. OpenAI 편집은 Responses API의 구조화된 JSON 응답을 검증한 후 로컬 FFmpeg에 전달합니다. 두 서비스의 키는 로컬 서버를 경유하며 외부에는 각각 해당 서비스 요청 때만 전송됩니다.

API 요청 주소는 `MINIMAX_API_BASE`, 편집 모델은 `OPENAI_EDIT_MODEL` 환경 변수로 변경할 수 있습니다. TTS 수동 편집은 기존 `QWEN3_TTS_URL`, `QWEN3_TTS_TOKEN_FILE`을 사용합니다. 미디어 작업 디렉터리는 `TD_EDITOR_WORK`로 지정할 수 있습니다.

## 공식 문서

- [MiniMax H3 영상 생성 API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)
- [MiniMax H3 작업 조회 API](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)
- [OpenAI 구조화 출력](https://developers.openai.com/api/docs/guides/structured-outputs)
