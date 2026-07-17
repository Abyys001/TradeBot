# Graph Report - .  (2026-06-26)

## Corpus Check
- Corpus is ~29,907 words - fits in a single context window. You may not need a graph.

## Summary
- 908 nodes · 1547 edges · 95 communities (77 shown, 18 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 121 edges (avg confidence: 0.59)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Tests|Tests]]
- [[_COMMUNITY_Subscriptions|Subscriptions]]
- [[_COMMUNITY_Views|Views]]
- [[_COMMUNITY_Tasks|Tasks]]
- [[_COMMUNITY_Readme|Readme]]
- [[_COMMUNITY_Client|Client]]
- [[_COMMUNITY_Session Store|Session Store]]
- [[_COMMUNITY_Interpreter|Interpreter]]
- [[_COMMUNITY_Models|Models]]
- [[_COMMUNITY_Views|Views]]
- [[_COMMUNITY_Parser|Parser]]
- [[_COMMUNITY_Package|Package]]
- [[_COMMUNITY_Order Router|Order Router]]
- [[_COMMUNITY_Semantic|Semantic]]
- [[_COMMUNITY_Ast Nodes|Ast Nodes]]
- [[_COMMUNITY_Consumers|Consumers]]
- [[_COMMUNITY_Tsconfig.Node|Tsconfig.Node]]
- [[_COMMUNITY_Apps|Apps]]
- [[_COMMUNITY_Candle Consumer|Candle Consumer]]
- [[_COMMUNITY_Hl Rate Limit|Hl Rate Limit]]
- [[_COMMUNITY_Indicators|Indicators]]
- [[_COMMUNITY_Hero.Png|Hero.Png]]
- [[_COMMUNITY_Tests|Tests]]
- [[_COMMUNITY_Icons.Svg|Icons.Svg]]
- [[_COMMUNITY_Tsconfig.App|Tsconfig.App]]
- [[_COMMUNITY_Vite.Svg|Vite.Svg]]
- [[_COMMUNITY_Vue.Svg|Vue.Svg]]
- [[_COMMUNITY_Readme|Readme]]
- [[_COMMUNITY_Models|Models]]
- [[_COMMUNITY_Hl Errors|Hl Errors]]
- [[_COMMUNITY_Favicon.Svg|Favicon.Svg]]
- [[_COMMUNITY_Base|Base]]
- [[_COMMUNITY_Hl Cloid|Hl Cloid]]
- [[_COMMUNITY_Usetoast|Usetoast]]
- [[_COMMUNITY_Tradingchart|Tradingchart]]
- [[_COMMUNITY_Tsconfig|Tsconfig]]
- [[_COMMUNITY_0001 Initial|0001 Initial]]
- [[_COMMUNITY_0001 Initial|0001 Initial]]
- [[_COMMUNITY_0001 Initial|0001 Initial]]
- [[_COMMUNITY_0001 Initial|0001 Initial]]
- [[_COMMUNITY_Entrypoint.Sh|Entrypoint.Sh]]
- [[_COMMUNITY_Asgi|Asgi]]
- [[_COMMUNITY_Urls|Urls]]
- [[_COMMUNITY_Wsgi|Wsgi]]
- [[_COMMUNITY_0002 Hyperliquid Order Id|0002 Hyperliquid Order Id]]
- [[_COMMUNITY_0002 Strategy Source Stra...|0002 Strategy Source Stra...]]
- [[_COMMUNITY_0003 Live Fields|0003 Live Fields]]
- [[_COMMUNITY_0004 Strategy Live Config|0004 Strategy Live Config]]
- [[_COMMUNITY_0005 Strategy Market Type|0005 Strategy Market Type]]
- [[_COMMUNITY_Layout|Layout]]
- [[_COMMUNITY_Docker-Compose|Docker-Compose]]
- [[_COMMUNITY_Docker-Compose|Docker-Compose]]

## God Nodes (most connected - your core abstractions)
1. `PineTransformer` - 31 edges
2. `Strategy` - 24 edges
3. `_pos()` - 24 edges
4. `compile()` - 23 edges
5. `ExecutionLog` - 21 edges
6. `SlidingWindow` - 21 edges
7. `LiveBroker` - 20 edges
8. `ExecutionContext` - 19 edges
9. `SemanticAnalyzer` - 19 edges
10. `normalize_coin()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `TradeBot Command Center` --conceptually_related_to--> `TradeBot`  [INFERRED]
  frontend/index.html → README.md
- `numpy 2.1.3` --implements--> `apps/transpiler`  [INFERRED]
  requirements.txt → README.md
- `pandas 2.2.3` --implements--> `apps/transpiler`  [INFERRED]
  requirements.txt → README.md
- `docker-compose.yml` --conceptually_related_to--> `web service`  [INFERRED]
  README.md → docker-compose.yml
- `Vue dashboard` --implements--> `Vue 3`  [INFERRED]
  README.md → frontend/README.md

## Import Cycles
- 1-file cycle: `apps/transpiler/parser.py -> apps/transpiler/parser.py`

## Hyperedges (group relationships)
- **Favicon Brand Color Palette** — public_favicon_purple_primary_color, public_favicon_violet_accent_color, public_favicon_lavender_highlight, public_favicon_cyan_accent [EXTRACTED 1.00]
- **Social Platform Brand Icons** — public_icons_bluesky_icon, public_icons_discord_icon, public_icons_github_icon, public_icons_x_icon [EXTRACTED 1.00]
- **Purple Stroked UI Icons** — public_icons_documentation_icon, public_icons_social_icon, public_icons_purple_stroke_color [EXTRACTED 1.00]
- **Stacked Platform Assembly** — assets_hero_top_wireframe_squircle, assets_hero_bottom_solid_squircle, assets_hero_dashed_corner_connectors, assets_hero_floating_stacked_platforms [EXTRACTED 1.00]
- **Vite Logo Visual Composition** — assets_vite_lightning_bolt, assets_vite_purple_brand_palette, assets_vite_cyan_accent, assets_vite_parenthesis_brackets, assets_vite_gaussian_blur_glow [EXTRACTED 1.00]
- **Vue Logo Composition** — assets_vue_path_outer_wings, assets_vue_path_inner_v, assets_vue_v_chevron_shape [EXTRACTED 1.00]

## Communities (95 total, 18 thin omitted)

### Community 0 - "Tests"
Cohesion: 0.06
Nodes (59): ProgramNode, ProgramNode, Indenter, Lark, _ohlcv_df(), Tests for Phase 3 live engine components., test_incremental_sma_matches_full_replay(), test_run_backtest_still_works_after_interpreter_refactor() (+51 more)

### Community 1 - "Subscriptions"
Cohesion: 0.06
Nodes (49): DataFrame, Redis, Command, Long-running Hyperliquid market data WebSocket feed., set_market_feed_heartbeat(), fetch_candles(), _normalize_rows(), Hyperliquid REST candle fetcher for live strategy warmup. (+41 more)

### Community 2 - "Views"
Cohesion: 0.08
Nodes (37): APIView, ping(), Celery application instance.  Broker / result backend / schedule are configure, Health-check task: confirms worker <-> broker round-trip., get_celery_status(), get_market_feed_status(), System health probes for the dashboard., publish_dashboard() (+29 more)

### Community 3 - "Tasks"
Cohesion: 0.08
Nodes (39): DataFrame, Strategy, publish_update(), Push one exchange update to the credential's Channels group., LiveIncrementalRunner, Seed historical candles, warmup interpreter state, then process live bars., BacktestAdmin, BacktestTradeInline (+31 more)

### Community 4 - "Readme"
Cohesion: 0.04
Nodes (49): candle-consumer service, frontend service, market-feed service, postgres service, postgres:16-alpine, redis service, redis:7-alpine, web service (+41 more)

### Community 5 - "Client"
Cohesion: 0.08
Nodes (32): api, Backtest, BacktestMetrics, BacktestTrade, Candle, ChartMarker, Credential, CredentialCreatePayload (+24 more)

### Community 6 - "Session Store"
Cohesion: 0.09
Nodes (26): Strategy, Redis, DataFrame, Incremental live strategy runner (Phase 3)., Process one closed candle. Returns True if processed, False if skipped., window_max_size(), _client(), delete_session() (+18 more)

### Community 7 - "Interpreter"
Cohesion: 0.12
Nodes (35): ProgramNode, Exception, ExecutionContext, ndarray, is_na(), History buffer for a path-dependent (`var`/`varip`/`:=`) variable., SeriesBuffer, as_array() (+27 more)

### Community 8 - "Models"
Cohesion: 0.12
Nodes (23): build_overview_payload(), Aggregate dashboard overview stats for the authenticated user., ExecutionLogAdmin, OrderRecordAdmin, ExecutionLog, Level, Meta, OrderRecord (+15 more)

### Community 9 - "Views"
Cohesion: 0.12
Nodes (21): Strategy, StrategyAdmin, StrategyStateAdmin, MarketType, Meta, A user's trading strategy configuration.      Phase 1 defines the schema only, Mutable runtime state for a strategy. One-to-one with Strategy., Status (+13 more)

### Community 10 - "Parser"
Cohesion: 0.11
Nodes (3): Transformer, PineTransformer, _pos()

### Community 11 - "Package"
Cohesion: 0.07
Nodes (27): dependencies, axios, lightweight-charts, monaco-editor, @monaco-editor/loader, pinia, vue, vue-i18n (+19 more)

### Community 12 - "Order Router"
Cohesion: 0.12
Nodes (5): LiveBroker, Routes orders to Hyperliquid via agent-signed transactions., In-memory simulated broker for backtests., SimBroker, Trade

### Community 13 - "Semantic"
Cohesion: 0.18
Nodes (9): ProgramNode, PineSemanticError, Scope or type violation found during semantic analysis., A parsed-but-rejected construct (e.g. plot/plotshape/bgcolor)., UnsupportedFeatureError, _children(), Yield child AST nodes for generic traversal., _Scope (+1 more)

### Community 14 - "Ast Nodes"
Cohesion: 0.13
Nodes (24): ArgNode, AssignNode, BinaryOpNode, BuiltinFunctionNode, ExprStatementNode, ForNode, HistoryAccessNode, IdentifierNode (+16 more)

### Community 15 - "Consumers"
Cohesion: 0.11
Nodes (12): AsyncWebsocketConsumer, dashboard_group_name(), Publish dashboard WebSocket events to per-user Channels groups., DashboardConsumer, ExchangeConsumer, Channels consumer pushing exchange updates to authenticated clients., Client WS endpoint: /ws/exchange/<credential_id>/      Joins the credential's, Handler for {"type": "exchange.update"} group messages. (+4 more)

### Community 16 - "Tsconfig.Node"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, moduleResolution, noEmit (+9 more)

### Community 17 - "Apps"
Cohesion: 0.14
Nodes (7): AccountsConfig, AppConfig, DashboardConfig, ExchangeConfig, ExecutionConfig, StrategiesConfig, TranspilerConfig

### Community 18 - "Candle Consumer"
Cohesion: 0.20
Nodes (8): BaseCommand, Command, Redis Pub/Sub consumer for Hyperliquid closed candles., CandleConsumer, Consume Hyperliquid candle Pub/Sub and fan out to Celery., Subscribe to ``hl:candles:*`` and enqueue ``process_live_bar_task``., _redis(), run_consumer()

### Community 19 - "Hl Rate Limit"
Cohesion: 0.19
Nodes (10): nonce_lock(), Rate limiting, retry, and nonce locking for Hyperliquid signed actions., Redis lock around signed exchange actions for one credential., Decorator: IP token bucket + exponential backoff on rate-limit errors., Run a signed HL action under nonce lock + rate limit., _redis(), signed_action(), _TokenBucket (+2 more)

### Community 20 - "Indicators"
Cohesion: 0.29
Nodes (11): crossover(), crossunder(), ema(), highest(), lowest(), Vectorized `ta.*` indicators (NumPy/pandas).  Each takes/returns a 1-D NumPy f, rma(), rsi() (+3 more)

### Community 21 - "Hero.Png"
Cohesion: 0.22
Nodes (11): Bottom Solid Squircle Platform, Dashed Corner Connector Lines, Floating Stacked Platform Composition, Isometric 3D Perspective, Layered Software Architecture Metaphor, Minimalist High-Contrast Style, Purple Crystalline Glowing Edge, Purple and Violet Accent Palette (+3 more)

### Community 22 - "Tests"
Cohesion: 0.25
Nodes (7): _hl_candle(), _make_cred(), Tests for the Hyperliquid exchange layer (no live network)., test_fetch_candles_normalizes_hl_response(), test_verify_credential_network_error_is_handled(), test_verify_credential_no_state_marks_inactive(), test_verify_credential_success_marks_active()

### Community 23 - "Icons.Svg"
Cohesion: 0.29
Nodes (11): Bluesky Icon, Dark Fill Color (#08060d), Discord Icon, Documentation Icon, GitHub Icon, Icons SVG Sprite Sheet, Open Book Documentation Glyph, Purple Stroke Color (#aa3bff) (+3 more)

### Community 24 - "Tsconfig.App"
Cohesion: 0.20
Nodes (9): compilerOptions, erasableSyntaxOnly, noFallthroughCasesInSwitch, noUnusedLocals, noUnusedParameters, tsBuildInfoFile, types, extends (+1 more)

### Community 25 - "Vite.Svg"
Cohesion: 0.25
Nodes (9): Cyan Accent Color, Dark Mode Color Adaptation, Frontend Build Tooling, Gaussian Blur Glow Effect, Lightning Bolt Glyph, Parenthesis Brackets, Purple-Violet Brand Palette, Vite (+1 more)

### Community 26 - "Vue.Svg"
Cohesion: 0.25
Nodes (9): Vue Brand Dark (#35495E), Vue Brand Green (#41B883), Iconify Logos Collection, Inner V Path, Outer Wing Paths, SVG Vector Graphic, V Chevron Shape, Vue.js Framework (+1 more)

### Community 27 - "Readme"
Cohesion: 0.22
Nodes (9): apps/transpiler, Lark parser, Phase 2 — Pine Script Transpiler, Pine Script v5, RestrictionLayer, SimBroker, lark 1.2.2, numpy 2.1.3 (+1 more)

### Community 28 - "Models"
Cohesion: 0.32
Nodes (5): AbstractUser, CustomUserAdmin, Custom user — defined from day one (swapping AUTH_USER_MODEL later is painful)., User, UserAdmin

### Community 29 - "Hl Errors"
Cohesion: 0.43
Nodes (6): HLErrorInfo, parse_exchange_response(), parse_order_status(), Hyperliquid exchange error code mapping., Return (exchange_oid, error_info) from a single HL order status dict., Parse all per-order statuses from an exchange API response.

### Community 30 - "Favicon.Svg"
Cohesion: 0.33
Nodes (7): Cyan Accent (#47bfff), TradeBot Favicon, Glossy Gradient Overlay, Lavender Highlight (#ede6ff), Lightning Bolt Silhouette, Primary Purple (#863bff), Violet Accent (#7e14ff)

### Community 31 - "Base"
Cohesion: 0.33
Nodes (3): Base settings shared by all environments.  Secrets and environment-specific va, Development settings., Production settings.  Layers 2/3 of the multi-layer credential protection live

### Community 32 - "Hl Cloid"
Cohesion: 0.40
Nodes (4): Cloid, pine_oid_to_cloid(), Map Pine strategy order ids to Hyperliquid client order ids (cloid)., Deterministic 128-bit cloid from a Pine order id string.

### Community 33 - "Usetoast"
Cohesion: 0.40
Nodes (3): Toast, toasts, ToastType

## Knowledge Gaps
- **138 isolated node(s):** `Migration`, `Cloid`, `T`, `Migration`, `Migration` (+133 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Strategy` connect `Views` to `Tests`, `Views`, `Tasks`, `Session Store`, `Models`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `normalize_coin()` connect `Subscriptions` to `Models`, `Views`, `Order Router`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `ExecutionLog` connect `Models` to `Tests`, `Views`, `Session Store`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Strategy` (e.g. with `Strategy` and `StrategyAdmin`) actually correct?**
  _`Strategy` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ExecutionLog` (e.g. with `ExecutionLogAdmin` and `OrderRecordAdmin`) actually correct?**
  _`ExecutionLog` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Migration`, `Custom user — defined from day one (swapping AUTH_USER_MODEL later is painful).`, `System health probes for the dashboard.` to the rest of the system?**
  _268 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.05621621621621622 - nodes in this community are weakly interconnected._