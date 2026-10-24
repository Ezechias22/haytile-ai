# HAYTILE AI — estati livrezon

Aplikasyon devlopman an konstwi dirèkteman nan depo sa a. Li pa yon senp mockup.
Pa gen piblikasyon piblik, AAB/IPA oswa peman reyèl ki deklare fèt.

## Fonksyon ki aplike ak konekte

- Next.js/React/TypeScript/Tailwind: akèy, 6 estidyo, bibliyotèk, kredi, paramèt,
  sant èd, kont ak panèl admin. Mak/icon orijinal, tèm nwa ak ekran responsive.
- FastAPI + PostgreSQL: migrasyon vèsyone, enskripsyon, login/logout, sesyon,
  pwofil/lang, ekspòtasyon ak efasman kont/done. Modpas hash scrypt; wòl admin.
- Bouyon tèks: sove, preview, kopi, download, chanje non, efase ak voye nan lòt estidyo.
- Upload imaj/odyo/videyo/tèks: verifye kalite ak gwosè, image decoding ak FFmpeg,
  preview/playback epi lyen prive siyen ki ekspire. Storage lokal prive oswa adapter S3.
- Queue PostgreSQL dirab + Redis wakeups, pwogrè, quality_check, completed/failed,
  retry limite. Travay entèwonp ki riske double billing mande rekonsilyasyon.
- Kredi: rezèvasyon atomik, konfimasyon pri, deduplication, debit apre fichye valide,
  lage rezèvasyon sou echèk, tranzaksyon ak grant admin audite. Imaj debaz: zewo debit.
- MiniDrama: pwojè, ID pèsonaj/sèn estab, aparans/rad/vwa/referans, nòt kontinwite,
  dyalòg egzak, lòd sèn, kontwòl vèsyon, jenerasyon yon sèn ak montaj klip chwazi.
- FFmpeg: normalizasyon ak montaj 8–180s, odyo, rezolisyon ak lòd klip verifye;
  pa gen stretching/loop pou kache klip ki twò kout. Final la antre nan bibliyotèk.
- Adapters Google pou tèks, imaj/referans, TTS, Lyria ak Omni. IDs pa aktive otomatikman.
- Expo Router/React Native: kont, estidyo, pwojè/sèn/pèsonaj, bibliyotèk, preview,
  medya, pataj/download, paramèt/lang ak kredi sou menm API a. Sesyon nan SecureStore.
- Fichye entèfas separe pou 9 lang, deteksyon lang ak chwa pèsistan, layout web RTL.
- Scripts enstalasyon/demaraj/tès, Dockerfiles/Compose, GitHub CI ak workflows EAS.

## Prèv validasyon

- 24 tès backend nan suite konplè a pase sou PostgreSQL: kont, izolasyon itilizatè, CSRF, downloads,
  upload, efasman, reset yon sèl fwa, pri/idempotency, depans an paralèl, refund,
  limit imaj, wòl/admin ak pwojè/revizyon.
- Tès montaj itilize videyo reyèl FFmpeg, verifye dire/rezolisyon/odyo **ak koulè
  sèn yo nan bon lòd**. Tès upload → queue → montaj → download epizòd pase.
- Yon lòt tès TLS/reset pase nan suite reset ki gen 3 tès la: 25 tès backend diferan an total.
- 4 tès zouti/lang pase: discovery pagination/erè ak konplè fichye 9 lang yo.
- Build pwodiksyon Next.js ak TypeScript web pase.
- TypeScript mobil ak export Hermes Android/iOS pase; vèsyon SDK soti nan matris
  Expo SDK 58. Pin react-dom 19.3.0 evite yon konfli peer sou fresh npm ci.
- Tès navigatè itilize backend reyèl. Rezilta final yo nan artifacts/VALIDATION.md.
- Alembic check: schema aktyèl la pa bezwen lòt migrasyon.

Tès AI backend yo itilize fixtures pou repons founisè a: yo verifye mekanis la,
pa kalite oswa aksè jenerasyon Google. Pa gen jenerasyon AI reyèl ki pase san kle.
Tès reset valide token/revokasyon; pa gen email SMTP reyèl ki voye.
Tradiksyon yo se yon premye vèsyon; revizyon imen ak tès aksesibilite aparèy rete itil.

## Sa ki rete pou fini pwodwi a

1. **Kle ak modèl kont:** kle Gemini a disponib kounye a. Yon discovery read-only reyisi: 60 modèl vizib. Jenerasyon reyèl, kota/pri kont ak kalite rete pou valide avèk yon plafon depans. Render bezwen kle sa a nan pwòp paramèt runtime li tou.
2. **Kalite medya:** lyrics egzak odyo, vwa senk lang, lip-sync otomatik, vizyon pou
   detekte defòmasyon/kontinwite, melanj mizik/narasyon ak soutit pa fini.
   Referans ak prompts ede; yo pa garanti figi, rad, dyalòg oswa bouch egzak.
3. **Peman:** Stripe/web, Apple/Google billing, abònman ak pakè kredi pa aplike.
   Pa gen bouton ki fè moun kwè yo achte kredi. Nenpòt entegrasyon mande tès sandbox.
4. **Idantite:** email reset mande SMTP; Google/Apple login, verifikasyon email,
   MFA admin ak kontwòl abi avanse pa aplike.
5. **Mobil/OTA:** sous ak bundles pare pou etap build la; pa gen aparèy oswa native
   build teste, AAB/IPA, rollout/rollback reyèl, store submission oswa EAS publication.
   Bezwen kont Expo, project ID ak signing/developer accounts.
6. **Pwodiksyon:** bezwen hosting/DNS/TLS, bucket prive konfigire, moderation,
   backup/restore drill, metrik/alert, rapò erè, audit sekirite ak revizyon LGPD/store.
   Dockerfiles/CI se konfigirasyon ki ekri; yo poko deplwaye oswa egzekite sou GitHub.

## Faz yo

| Faz | Estati aktyèl |
|---|---|
| 1 | Dokiman Google aktyèl verifye; chwa kont/pri final ak benchmark GPU rete |
| 2 | UI/UX web + mobil, mak ak 9 fichye lang; QA imen/aparèy rete |
| 3 | Backend/kont/bibliyotèk/migrasyon travay; federasyon/MFA/SMTP pwodiksyon rete |
| 4 | Imaj zewo kredi aplike; adapter Google ekri, jenerasyon reyèl pa teste |
| 5 | Tèks/TTS konekte; verifikasyon sou kont ak kalite lang rete |
| 6 | Lyria adapter ekri; vokal/lyrics/lisans reyèl pa valide |
| 7 | Queue ak montaj 8–180s teste; jenerasyon videyo Google/kalite pa valide |
| 8 | Editè pwojè/sèn/pèsonaj ak montaj teste; lip-sync ak QC vizyèl rete |
| 9 | Ledger/retry/refund teste; peman ak abònman pa aplike |
| 10 | Admin debaz, CI ak konfig EAS ekri; native builds/OTA reyèl rete |
| 11 | Pa lanse: bezwen sèvis ekstèn, revizyon pwodiksyon ak tès final |

Enstriksyon kontinye: gade DEPLOYMENT.md. Pa deklare tout pwodwi a fini ak lis sa a.

## Preparasyon Render

`render.yaml` ak imaj Docker Render la prepare. Imaj la bati epi 3 tès navigatè sou kontenè a pase. Worker reyèl la fè montaj; disk/DB/sesyon rete apre restart. Kle Render disponib, listing sèvis yo mache; listing owners/PostgreSQL retounen HTTP 403 HTML. Pa gen sèvis Render kreye ankò. Konfigirasyon pwopoze a se anviwon $31.25/mwa anvan AI/taks/depase kota, li bezwen konfimasyon operatè a.

## Chwa aktyèl: Render gratis

Itilizatè a refize plan Render peye pou kounye a. `render.yaml` ranplase pwopozisyon peye a avèk yon sèl sèvis gratis, san disk oswa bazdone peye. Free beta gen avètisman sou done tanporè nan 9 lang. Jenerasyon AI ak grant kredi peye bloke sou SQLite. Demann bazdone Render free la retounen HTTP 403; pa gen fallback peye.
