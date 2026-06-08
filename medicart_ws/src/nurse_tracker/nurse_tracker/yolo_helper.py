"""ward_robot perception 용 YoloHelper — ByteTrack 추적 래퍼.

규칙:
  1. 직접 만든 모델 경로가 없으면 미감지 상태 유지(크래시 금지)
  2. yolov8n.pt 같은 기본 모델 이름은 Ultralytics에 그대로 전달
"""

from pathlib import Path


class YoloHelper:
    """perception(추종/순찰) 용 YOLO 래퍼.

    모델 로드를 생성자에서 시도하고, 실패(파일 없음/ultralytics 미설치)해도
    예외를 던지지 않는다. detect()는 모델이 없으면 빈 리스트를 돌려줘
    노드가 '미탐지' 상태로 정상 동작하게 한다(모델 학습 전에도 기동 가능).
    """

    def __init__(self, model_path, conf=0.45, logger=None):
        self._conf = float(conf)
        self._logger = logger
        self.model = self._load(model_path)

    def _log(self, msg):
        if self._logger is not None:
            self._logger.info(msg)
        else:
            print(f"[yolo_helper] {msg}")

    def _load(self, model_path):
        if not model_path:
            self._log("model_path 비어 있음 → 미탐지 모드")
            return None
        try:
            from ultralytics import YOLO
        except ImportError:
            self._log("ultralytics 미설치 → 미탐지 모드 (pip install ultralytics)")
            return None

        model_file = Path(str(model_path)).expanduser()
        if model_file.is_absolute() or "/" in str(model_path):
            if not model_file.exists():
                self._log(f"모델 파일 없음: {model_file} → 미탐지 모드")
                return None
            source = str(model_file)
        else:
            source = str(model_path)   # yolov8n.pt 같은 기본 이름

        try:
            model = YOLO(source)
            self._log(f"YOLO 모델 로드 완료: {source}")
            return model
        except Exception as e:
            self._log(f"YOLO 로드 실패: {e} → 미탐지 모드")
            return None

    def detect(self, img):
        """ByteTrack 추적 추론 → [[x1, y1, x2, y2, conf, class_name, track_id], ...].

        프레임 내 모든 박스를 반환하고, 각 박스에 프레임 간 유지되는 track_id를 부여한다
        (트래킹 실패 시 track_id=-1). 모델이 없으면 빈 리스트.
        perception.PersonTracker가 이 7요소 형식을 가정한다.
        """
        if self.model is None:
            return []
        try:
            # persist=True → 프레임 간 ID 유지. ByteTrack은 ultralytics 내장.
            results = self.model.track(
                img, conf=self._conf, persist=True,
                tracker="bytetrack.yaml", verbose=False,
            )
        except Exception as e:
            self._log(f"추적 추론 오류: {e}")
            return []

        boxes = []
        for result in results:
            names = result.names
            for b in result.boxes:
                x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
                conf = float(b.conf[0])
                cls = names.get(int(b.cls[0]), str(int(b.cls[0])))
                track_id = int(b.id[0]) if b.id is not None else -1
                boxes.append([x1, y1, x2, y2, conf, cls, track_id])
        return boxes
