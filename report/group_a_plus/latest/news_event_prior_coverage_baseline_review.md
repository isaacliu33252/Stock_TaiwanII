# News Event Prior Coverage Baseline Review

- Generated: `2026-08-21T08:14:01`
- Decision: `do_not_promote_keep_shadow`
- Policy: `research_only_no_target_weight_change`
- Target weight change allowed: `False`

## Coverage

- raw_news_rows: `14512`
- event_days: `1065`
- event_days_with_returns: `725`
- date_min: `2025-01-02`
- date_max: `2026-08-18`
- min_events_required_per_cell: `20`
- quiet_days_with_returns: `14581`

## Quiet Baseline

- H1: status=`ok`, n=`14581`, mean_return=`0.0007530081132169069`, mean_abs_return=`0.010523207260226602`
- H5: status=`ok`, n=`14581`, mean_return=`0.0036335257951243846`, mean_abs_return=`0.02550113606013896`
- H20: status=`ok`, n=`14514`, mean_return=`0.014471627699249007`, mean_abs_return=`0.05874757934983257`

## Blockers

- `no_event_bucket_materially_beats_coverage_baseline`

## Event Buckets

### etf_structure
- event days: `217`
- H1: status=`ok`, n=`217`, mean_return=`0.0010756356291294633`, excess_return_vs_quiet=`0.0003226275159125564`, excess_return_vs_coverage=`-0.0019109591383451553`, mean_abs_return=`0.013421594607725296`, excess_abs_vs_quiet=`0.0028983873474986935`, excess_abs_vs_coverage=`-0.002645915510301581`
- H5: status=`ok`, n=`215`, mean_return=`0.01092337073668132`, excess_return_vs_quiet=`0.007289844941556935`, excess_return_vs_coverage=`-0.002922983099425465`, mean_abs_return=`0.03311515245077112`, excess_abs_vs_quiet=`0.007614016390632156`, excess_abs_vs_coverage=`-0.005252964438007143`
- H20: status=`ok`, n=`213`, mean_return=`0.04918194133887968`, excess_return_vs_quiet=`0.034710313639630674`, excess_return_vs_coverage=`-0.004290151871451556`, mean_abs_return=`0.08737124804938491`, excess_abs_vs_quiet=`0.028623668699552345`, excess_abs_vs_coverage=`-0.0030292160773255777`

### fund_flow_positioning
- event days: `140`
- H1: status=`ok`, n=`140`, mean_return=`0.0050714206850273735`, excess_return_vs_quiet=`0.004318412571810467`, excess_return_vs_coverage=`0.002084825917552755`, mean_abs_return=`0.017385185816810467`, excess_abs_vs_quiet=`0.006861978556583865`, excess_abs_vs_coverage=`0.0013176756987835908`
- H5: status=`ok`, n=`140`, mean_return=`0.018658846423450733`, excess_return_vs_quiet=`0.015025320628326348`, excess_return_vs_coverage=`0.004812492587343948`, mean_abs_return=`0.0437751168131256`, excess_abs_vs_quiet=`0.018273980752986637`, excess_abs_vs_coverage=`0.005406999924347337`
- H20: status=`ok`, n=`139`, mean_return=`0.05667560800888042`, excess_return_vs_quiet=`0.04220398030963141`, excess_return_vs_coverage=`0.0032035147985491827`, mean_abs_return=`0.08508797625432962`, excess_abs_vs_quiet=`0.026340396904497056`, excess_abs_vs_coverage=`-0.005312487872380867`

### hard_quantified
- event days: `30`
- H1: status=`ok`, n=`30`, mean_return=`0.005525214131500533`, excess_return_vs_quiet=`0.0047722060182836265`, excess_return_vs_coverage=`0.0025386193640259147`, mean_abs_return=`0.01324944754688692`, excess_abs_vs_quiet=`0.0027262402866603183`, excess_abs_vs_coverage=`-0.002818062571139956`
- H5: status=`ok`, n=`30`, mean_return=`0.006068640025631766`, excess_return_vs_quiet=`0.0024351142305073814`, excess_return_vs_coverage=`-0.007777713810475019`, mean_abs_return=`0.02335713458753342`, excess_abs_vs_quiet=`-0.002144001472605541`, excess_abs_vs_coverage=`-0.01501098230124484`
- H20: status=`ok`, n=`30`, mean_return=`0.039137570402326835`, excess_return_vs_quiet=`0.02466594270307783`, excess_return_vs_coverage=`-0.014334522808004402`, mean_abs_return=`0.04761306230428304`, excess_abs_vs_quiet=`-0.011134517045549526`, excess_abs_vs_coverage=`-0.04278740182242745`

### investor_education
- event days: `15`
- H1: status=`insufficient_data`, n=`15`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H5: status=`insufficient_data`, n=`15`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H20: status=`insufficient_data`, n=`15`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`

### legal_regulatory
- event days: `1`
- H1: status=`insufficient_data`, n=`1`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H5: status=`insufficient_data`, n=`1`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H20: status=`insufficient_data`, n=`1`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`

### macro_through_stock
- event days: `20`
- H1: status=`ok`, n=`20`, mean_return=`8.413180270051557e-05`, excess_return_vs_quiet=`-0.0006688763105163914`, excess_return_vs_coverage=`-0.002902462964774103`, mean_abs_return=`0.012657600215720499`, excess_abs_vs_quiet=`0.0021343929554938964`, excess_abs_vs_coverage=`-0.003409909902306378`
- H5: status=`insufficient_data`, n=`17`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H20: status=`insufficient_data`, n=`16`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`

### price_commentary
- event days: `6`
- H1: status=`insufficient_data`, n=`6`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H5: status=`insufficient_data`, n=`6`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H20: status=`insufficient_data`, n=`6`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`

### soft_story
- event days: `7`
- H1: status=`insufficient_data`, n=`7`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H5: status=`insufficient_data`, n=`7`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`
- H20: status=`insufficient_data`, n=`7`, mean_return=`None`, excess_return_vs_quiet=`None`, excess_return_vs_coverage=`None`, mean_abs_return=`None`, excess_abs_vs_quiet=`None`, excess_abs_vs_coverage=`None`

### unknown
- event days: `289`
- H1: status=`ok`, n=`289`, mean_return=`0.003273112061666063`, excess_return_vs_quiet=`0.002520103948449156`, excess_return_vs_coverage=`0.00028651729419144466`, mean_abs_return=`0.017753110182095574`, excess_abs_vs_quiet=`0.007229902921868972`, excess_abs_vs_coverage=`0.0016856000640686972`
- H5: status=`ok`, n=`284`, mean_return=`0.015242129360326788`, excess_return_vs_quiet=`0.011608603565202403`, excess_return_vs_coverage=`0.0013957755242200026`, mean_abs_return=`0.04142903228423643`, excess_abs_vs_quiet=`0.01592789622409747`, excess_abs_vs_coverage=`0.0030609153954581705`
- H20: status=`ok`, n=`282`, mean_return=`0.055596884967683544`, excess_return_vs_quiet=`0.04112525726843454`, excess_return_vs_coverage=`0.0021247917573523067`, mean_abs_return=`0.09968225659188609`, excess_abs_vs_quiet=`0.040934677242053526`, excess_abs_vs_coverage=`0.009281792465175603`

