// 빌드 전 자동 실행(prebuild): common/robot.env 의 ROBOT_NAMESPACE 를
// .env.production.local 의 NEXT_PUBLIC_PRIMARY_NS 로 동기화 → 프론트 namespace 단일소스.
const fs = require("fs");
const path = require("path");

const envPath = path.resolve(__dirname, "../../../common/robot.env");
let ns = "robot3";
try {
  const m = fs.readFileSync(envPath, "utf8").match(/^ROBOT_NAMESPACE=(\S+)/m);
  if (m) ns = m[1];
} catch (e) {
  console.warn("[sync-ns] robot.env 못 읽음 → 기본 robot3:", e.message);
}
fs.writeFileSync(path.resolve(__dirname, "../.env.production.local"), `NEXT_PUBLIC_PRIMARY_NS=${ns}\n`);
console.log(`[sync-ns] NEXT_PUBLIC_PRIMARY_NS=${ns}`);
