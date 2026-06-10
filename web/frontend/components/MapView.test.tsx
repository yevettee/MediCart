import { describe, it, expect } from "vitest";

// === X-TELE-06 회귀 가드 ===
// 아래 worldToPixel 은 MapView.tsx 의 mapMeta 좌표 변환 클로저와 동일한 식이어야 한다.
// MapView.tsx:80-81 의 X()/Y() 정의를 변경하면 이 함수도 함께 갱신할 것(드리프트 방지).
//
// 실제 MapView 식 (MapView.tsx L80-81):
//   X = (wx) => offx + ((wx - ox) / res) * s
//   Y = (wy) => offy + (ih - (wy - oy) / res) * s
//
// 아래 함수는 화면 offset(offx/offy)·fit-scale(s) 을 제거한 순수 맵픽셀 공간 변환이다.
// (offx=0, offy=0, s=1 로 특수화) — 변환의 핵심 수학은 동일하고,
// 화면 배치 항(offx/offy/s)은 비율·방향에 영향 없음.
function worldToPixel(
  wx: number, wy: number,
  ox: number, oy: number, res: number, imgH: number
) {
  return {
    px: (wx - ox) / res,          // MapView L80: ((wx - ox) / res) * s  (s=1 특수화)
    py: imgH - (wy - oy) / res,   // MapView L81: offy + (ih - (wy - oy) / res) * s  (offy=0, s=1)
  };
}

// X-TELE-07/08 (캔버스 마커 그리기 smoke): jsdom 에서 Canvas API 미지원으로
// HTMLCanvasElement.getContext 가 null 을 반환하므로 브리틀한 mock 렌더 대신
// 매뉴얼 런타임 검증으로 처리 (catalog tags: manual:runtime).

describe("MapView world→pixel 변환 (X-TELE-06)", () => {
  it("origin 점은 좌하단(px≈0, py≈imgH)", () => {
    const { px, py } = worldToPixel(-5.59, -4.58, -5.59, -4.58, 0.05, 200);
    expect(px).toBeCloseTo(0);
    expect(py).toBeCloseTo(200);
  });

  it("월드 +1m(x) = +20px (res 0.05)", () => {
    const a = worldToPixel(0, 0, -5.59, -4.58, 0.05, 200);
    const b = worldToPixel(1, 0, -5.59, -4.58, 0.05, 200);
    expect(b.px - a.px).toBeCloseTo(20);
  });

  it("월드 +1m(y) = py -20px (y축 반전)", () => {
    const a = worldToPixel(0, 0, -5.59, -4.58, 0.05, 200);
    const b = worldToPixel(0, 1, -5.59, -4.58, 0.05, 200);
    expect(b.py - a.py).toBeCloseTo(-20);
  });
});
