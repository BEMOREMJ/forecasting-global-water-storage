# Post-closeout P3-E1 diagnostic candidate

**PASS for local diagnostic generation; P3-E1 remains non-promoted.** Frozen OOF is 0.571686 and h6 remains failed (.655841 > .648339); no validation, optimizer, or repair reran.

Weights (persistence/Phase2/M1/M2/M3B/M4): G1 `.372196/.012825/.000000/.426540/.063818/.124621`; G23 `.102602/.000000/.000000/.618763/.140815/.137819`; G47 `.021291/.003768/.121067/.434120/.170414/.249340`. They are exact directional means, nonnegative and unit-sum. Configuration SHA: `c85474b56405335770b087c82739c6b340f46ecfd325a18d04384453378668a4`.

Reused: persistence, Phase 2, P3-M3B. Newly fitted once: P3-M1 (59.24 s, 1,447.91 MB), P3-M2 (85.75 s, 2,781.60 MB), and P3-M4 G1/G23/G47 (57.31 s, 2,025.81 MB). Full component hashes and sizes are in `reports/phase3_p3e1_production_manifest.json`. Total runtime: 241.70 s.

Routing: G1 94,048; G23 109,353; G47 77,560. All 280,961 official IDs aligned with safe observed anchors, no recursion/fallback/clipping/post-processing. Candidate `submissions/phase3_p3e1_guarded_ensemble_diagnostic.csv` has exactly `ID,Target`, SHA `7e8a70bd8410988b892c1603959eabcc8921cfae78a26a526e0de5eab2d93efc`; mean -.076287, SD .522600, range [-2.393018,2.487533]. Contract passed. Generated, diagnostic, not uploaded; P3-M3B primary SHA `b9b1b95e...7f11e` is unchanged.
