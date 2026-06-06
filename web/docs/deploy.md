# 배포 (systemd + Cloudflare 터널)

- `deploy/medicart-backend.service` / `medicart-frontend.service` / `medicart-tunnel.service` 를
  `/etc/systemd/system/` 에 링크 후 `systemctl enable --now`.
- backend는 `.env`(EnvironmentFile)로 FB_CRED/FB_DB_URL 주입. 프론트는 빌드 env로 NS 설정.
- 공개 호스팅은 Cloudflare 터널(setup-tunnel.sh). 비밀번호 게이트(INTEL_PASSWORD)로 접근 통제(데모).
- 구 intel-*.service 는 legacy/ 참고.
