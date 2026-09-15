# LEILA Wave 2 research

On 6,346 matched held-out games, Tier 1 + Wave 2 changes margin MAE by +0.107 points, log loss by +0.03594, and winner accuracy by -0.69 percentage points. The experiment does not justify promoting these features into production. Distinct descriptive and matchup statistics still belong on Exploratory.

## Scope and decision

Completed-season evaluation: 2014–2019 and 2021–2025. The incomplete 2026 season and exceptional 2020 season are excluded. Production Adj. Net, Adj. Off, Adj. Def, ASM, predictions, and CFP probabilities were not modified.

The eight distinct Wave 2 statistics remain eligible for the Exploratory page regardless of predictive lift. Points per Scoring Opportunity remains excluded as the previously established duplicate of Finishing Drives. Publication and read-back verification for 12 seasons were completed in the supplied Claude handoff; this follow-up changes research only.

## Method

Pregame rates sum raw numerators and denominators from strictly earlier canonical season-type/week partitions, with a denominator floor of 10. No current-week outcomes, future outcomes, full-season averages, or cross-season training enter predictions. Counters are added once per field. Models reset each season, with at least 20 prior eligible game rows (40 team-game rows for situational tests). Canonical week partitions preserve the earlier generic harness; their coarser week grouping can withhold some chronologically earlier games, never add a future week. Early-season and missing-feature games are excluded transparently by model sample size.

The historical baseline is the previous research harness: pregame possession-based Adj Net difference plus intercept, with shrinkage 10 in the rating fit. It has no explicit venue variable; its intercept supplies the historical average home advantage. It is not a complete replay of every current production prediction input. Standardized OLS (ridge 1e-6) and the original 250-step logistic optimizer are reproduced numerically by a regression test. Baseline and challenger predictions are evaluated on identical held-out games. The JSON also includes a baseline fitted on each challenger's training population.

Generic additive pairing uses both home-away offense and defense differences. The interaction is z(home offense) × z(away defense) − z(away offense) × z(home defense), using training-only scales; this corrects the handoff's product of the two differences. The defense's allowed-rate sign is learned rather than mislabeled as quality.

Grouped models tune ridge penalties {1,10,100} and logistic L2 penalties {.001,.01,.1} on the last quarter of prior training weeks, fitting scaling on the earlier inner-training weeks only. With fewer than four training weeks, fixed defaults apply. An additional common-population tuned-baseline control isolates feature value from regularization. Logistic regularization uses the historical optimizer, so finite-iteration optimization remains a limitation.

Situational models compare prior league mean, offense only, opponent defense only, additive, interaction, 50-tree depth-2 boosting, and a three-knot quadratic additive spline with ridge 10. Nonlinear settings are fixed, with no search. Rates are scored without clipping so the linear comparison stays consistent. Targets are unweighted team-game rates; small target denominators increase noise. Offensive points use final team points; points per possession uses offensive drive points / resolved point possessions, excluding defensive/special-teams scores from the numerator.

Uncertainty uses 1,000 paired season-week block bootstrap draws, preserving both offenses from each game and shared week effects. Intervals are 95%; positive improvements mean lower error or higher accuracy. Blocks do not fully account for teams recurring across weeks, and no multiple-comparison correction is applied. Season consistency is therefore also required. R² is pooled held-out 1−SSE/SST, not improvement relative to Adj Net. Same-game downstream correlations and split-half stability are descriptive checks, never evidence of pregame prediction.

## Generic game prediction

Each row reports a challenger against its own identical-game historical baseline. Δ accuracy is percentage points; all other deltas are challenger minus baseline (negative error deltas are better).

| Model | Games | Δ accuracy pp | Δ log loss | Δ Brier | Δ MOV MAE | Δ RMSE | Pearson | OOS R² | Seasons MAE better/worse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cleanDrive_additive | 6,964 | +0.057 | +0.00329 | +0.00110 | +0.0629 | +0.0769 | 0.561 | 0.311 | 1/10 |
| cleanDrive_interaction | 6,964 | -0.101 | +0.00416 | +0.00127 | +0.0590 | +0.0835 | 0.560 | 0.310 | 0/11 |
| combined | 6,346 | -0.693 | +0.03594 | +0.01002 | +0.1071 | +0.1695 | 0.551 | 0.303 | 2/9 |
| driveKiller_additive | 6,346 | -0.567 | +0.00838 | +0.00262 | +0.0536 | +0.0764 | 0.558 | 0.311 | 4/7 |
| driveKiller_interaction | 6,346 | -0.410 | +0.01137 | +0.00334 | +0.0811 | +0.0986 | 0.557 | 0.309 | 4/7 |
| explosive_additive | 7,026 | -0.014 | +0.00082 | +0.00033 | +0.0354 | +0.0503 | 0.562 | 0.312 | 3/8 |
| explosive_interaction | 7,026 | -0.128 | +0.00434 | +0.00133 | +0.0627 | +0.0905 | 0.559 | 0.309 | 3/8 |
| failure_additive | 7,027 | -0.327 | +0.00293 | +0.00127 | +0.0616 | +0.0681 | 0.561 | 0.311 | 4/7 |
| failure_interaction | 7,027 | -0.441 | +0.00502 | +0.00187 | +0.0763 | +0.0985 | 0.559 | 0.308 | 3/8 |
| individual_cleanDriveRate | 6,964 | -0.072 | +0.00154 | +0.00065 | +0.0264 | +0.0440 | 0.563 | 0.313 | 4/7 |
| individual_cleanDriveRateAllowed | 6,970 | +0.158 | +0.00225 | +0.00066 | +0.0343 | +0.0337 | 0.563 | 0.314 | 2/9 |
| individual_driveKillerRate | 6,361 | -0.519 | +0.00722 | +0.00240 | +0.0118 | +0.0321 | 0.562 | 0.314 | 7/4 |
| individual_driveKillerRateForced | 6,361 | -0.424 | +0.00367 | +0.00125 | +0.0237 | +0.0353 | 0.562 | 0.315 | 4/7 |
| individual_explosiveDependency | 7,026 | -0.114 | +0.00102 | +0.00043 | +0.0246 | +0.0286 | 0.563 | 0.314 | 3/8 |
| individual_failureBurden | 7,027 | -0.043 | +0.00181 | +0.00069 | +0.0416 | +0.0433 | 0.563 | 0.313 | 2/9 |
| individual_failurePressure | 7,027 | -0.356 | +0.00129 | +0.00067 | +0.0162 | +0.0180 | 0.564 | 0.315 | 4/7 |
| individual_nonExplosiveEpaPerPlay | 7,027 | +0.057 | +0.00159 | +0.00069 | +0.0178 | +0.0304 | 0.563 | 0.314 | 4/7 |
| tier1 | 6,972 | +0.287 | +0.00307 | +0.00100 | -0.0385 | +0.0269 | 0.565 | 0.315 | 8/3 |
| wave2 | 6,346 | -0.646 | +0.02154 | +0.00683 | +0.1318 | +0.2040 | 0.549 | 0.300 | 2/9 |

## Grouped features: matched training and test populations

All four models use the same feature-complete population and tuning grid. The reference below is the independently tuned Adj Net-only model.

| Group | Games | Δ accuracy pp | Δ log loss | Δ MAE | MAE improvement 95% CI |
|---|---:|---:|---:|---:|---|
| combined | 6,346 | -0.772 | +0.03258 | +0.1391 | [-0.24296900807041452, -0.042853469168731714] |
| ridge_baseline | 6,346 | +0.000 | +0.00000 | +0.0000 | [0.0, 0.0] |
| tier1 | 6,346 | -0.205 | +0.00901 | -0.0088 | [-0.0450785462188061, 0.06232290692070933] |
| wave2 | 6,346 | -0.725 | +0.01818 | +0.1639 | [-0.24945299329120527, -0.08449184997501726] |

### Failure Pressure after efficiency controls

After pregame offensive and defensive EPA/play and Success Rate differences, adding Failure Pressure changes MAE by +0.0105 points and log loss by +0.00065. MAE improvement 95% CI: [-0.031402207326255746, 0.010157265359111307]. This is an explicitly separate sensitivity baseline.

## Situational matchup prediction

| Target | Model | Team-games | MAE | RMSE | Pearson | OOS R² |
|---|---|---:|---:|---:|---:|---:|
| cleanDriveRate | additive | 13,865 | 0.1273 | 0.1587 | 0.174 | 0.030 |
| cleanDriveRate | boosting | 13,865 | 0.1282 | 0.1598 | 0.143 | 0.017 |
| cleanDriveRate | defense | 13,865 | 0.1280 | 0.1594 | 0.144 | 0.021 |
| cleanDriveRate | interaction | 13,865 | 0.1273 | 0.1587 | 0.174 | 0.030 |
| cleanDriveRate | mean | 13,865 | 0.1288 | 0.1604 | 0.101 | 0.009 |
| cleanDriveRate | offense | 13,865 | 0.1281 | 0.1596 | 0.138 | 0.019 |
| cleanDriveRate | spline | 13,865 | 0.1274 | 0.1588 | 0.171 | 0.029 |
| cleanDriveRate_points | additive | 13,865 | 9.9577 | 12.3980 | 0.427 | 0.182 |
| cleanDriveRate_pointsPerPossession | additive | 13,865 | 0.7982 | 0.9997 | 0.406 | 0.164 |
| driveKillerRate | additive | 12,650 | 0.1375 | 0.1736 | 0.162 | 0.026 |
| driveKillerRate | boosting | 12,650 | 0.1387 | 0.1752 | 0.119 | 0.009 |
| driveKillerRate | defense | 12,650 | 0.1388 | 0.1752 | 0.096 | 0.009 |
| driveKillerRate | interaction | 12,650 | 0.1376 | 0.1738 | 0.155 | 0.024 |
| driveKillerRate | mean | 12,650 | 0.1397 | 0.1762 | -0.010 | -0.002 |
| driveKillerRate | offense | 12,650 | 0.1386 | 0.1748 | 0.114 | 0.013 |
| driveKillerRate | spline | 12,650 | 0.1377 | 0.1741 | 0.148 | 0.021 |
| driveKillerRate_points | additive | 12,650 | 9.8895 | 12.2941 | 0.436 | 0.190 |
| driveKillerRate_pointsPerPossession | additive | 12,650 | 0.7909 | 0.9909 | 0.419 | 0.176 |
| explosiveDependency | additive | 13,977 | 0.1129 | 0.1412 | 0.178 | 0.030 |
| explosiveDependency | boosting | 13,977 | 0.1137 | 0.1421 | 0.138 | 0.018 |
| explosiveDependency | defense | 13,977 | 0.1139 | 0.1425 | 0.111 | 0.012 |
| explosiveDependency | interaction | 13,977 | 0.1130 | 0.1413 | 0.171 | 0.028 |
| explosiveDependency | mean | 13,977 | 0.1146 | 0.1433 | 0.037 | 0.001 |
| explosiveDependency | offense | 13,977 | 0.1135 | 0.1420 | 0.140 | 0.019 |
| explosiveDependency | spline | 13,977 | 0.1129 | 0.1412 | 0.174 | 0.030 |
| explosiveDependency_points | additive | 13,977 | 9.9328 | 12.3626 | 0.433 | 0.187 |
| explosiveDependency_pointsPerPossession | additive | 13,977 | 0.7968 | 0.9976 | 0.411 | 0.169 |
| explosivePlayRate | additive | 13,983 | 0.0381 | 0.0480 | 0.270 | 0.066 |
| explosivePlayRate | boosting | 13,983 | 0.0383 | 0.0484 | 0.230 | 0.053 |
| explosivePlayRate | defense | 13,983 | 0.0386 | 0.0488 | 0.202 | 0.037 |
| explosivePlayRate | interaction | 13,983 | 0.0381 | 0.0481 | 0.266 | 0.065 |
| explosivePlayRate | mean | 13,983 | 0.0393 | 0.0497 | 0.028 | -0.000 |
| explosivePlayRate | offense | 13,983 | 0.0388 | 0.0490 | 0.175 | 0.028 |
| explosivePlayRate | spline | 13,983 | 0.0380 | 0.0480 | 0.267 | 0.068 |
| explosivePlayRate_points | additive | 13,983 | 9.9310 | 12.3608 | 0.433 | 0.187 |
| explosivePlayRate_pointsPerPossession | additive | 13,983 | 0.7966 | 0.9974 | 0.411 | 0.169 |
| failureBurden | additive | 13,978 | 0.0699 | 0.0891 | 0.255 | 0.061 |
| failureBurden | boosting | 13,978 | 0.0704 | 0.0897 | 0.218 | 0.048 |
| failureBurden | defense | 13,978 | 0.0713 | 0.0907 | 0.167 | 0.027 |
| failureBurden | interaction | 13,978 | 0.0699 | 0.0891 | 0.254 | 0.061 |
| failureBurden | mean | 13,978 | 0.0722 | 0.0918 | 0.067 | 0.003 |
| failureBurden | offense | 13,978 | 0.0709 | 0.0904 | 0.184 | 0.033 |
| failureBurden | spline | 13,978 | 0.0698 | 0.0890 | 0.255 | 0.064 |
| failureBurden_points | additive | 13,978 | 9.9436 | 12.3706 | 0.431 | 0.186 |
| failureBurden_pointsPerPossession | additive | 13,978 | 0.7928 | 0.9930 | 0.420 | 0.176 |

### Offensive output forecasts

These compare a team's signed pregame Adj Net control against that control plus its offense/opponent-defense tendencies. This output-specific baseline is less complete than a dedicated offensive scoring model; small gains here do not establish win/margin value or production readiness.

| Pair / target | Baseline MAE | Additive MAE | Improvement 95% CI | Seasons better/worse |
|---|---:|---:|---|---:|
| cleanDriveRate_points | 9.9667 | 9.9577 | [-0.0048866850086179145, 0.0232309158649889] | 7/4 |
| cleanDriveRate_pointsPerPossession | 0.7992 | 0.7982 | [-0.00010926457642386413, 0.001971493480547796] | 5/6 |
| driveKillerRate_points | 9.9688 | 9.8895 | [0.05890421287153267, 0.10069333735662814] | 10/1 |
| driveKillerRate_pointsPerPossession | 0.7998 | 0.7909 | [0.006757627668634454, 0.011116385840611613] | 11/0 |
| explosiveDependency_points | 9.9692 | 9.9328 | [0.018985290703405624, 0.05195861071651814] | 10/1 |
| explosiveDependency_pointsPerPossession | 0.7997 | 0.7968 | [0.0015077051726220118, 0.004082300960672257] | 8/3 |
| failureBurden_points | 9.9694 | 9.9436 | [0.008076110885898016, 0.042702629386828485] | 9/2 |
| failureBurden_pointsPerPossession | 0.7997 | 0.7928 | [0.005302010572850506, 0.008531348921977428] | 11/0 |

The defensive explosive counterpart is the existing canonical explosive-play rate allowed. It measures frequency allowed, not a newly invented defensive EPA-share metric. Explosive Dependency is already the positive explosive EPA share, so it is not counted as a second independent target under another name.

### Additive and nonlinear uncertainty

| Target | Comparison | MAE improvement | 95% CI | Seasons better/worse |
|---|---|---:|---|---:|
| cleanDriveRate | additive_vs_offense | +0.00078 | [0.0005265663573304537, 0.0010160733491107968] | 11/0 |
| cleanDriveRate | additive_vs_defense | +0.00068 | [0.00046703749316825353, 0.0009033886776219995] | 10/1 |
| cleanDriveRate | additive_vs_mean | +0.00145 | [0.0011081131166990545, 0.001812994318358331] | 11/0 |
| cleanDriveRate | interaction_vs_additive | -0.00002 | [-8.309162542830463e-05, 4.426985901631705e-05] | 6/5 |
| cleanDriveRate | boosting_vs_additive | -0.00088 | [-0.0013129888222797221, -0.00047960412439933644] | 0/11 |
| cleanDriveRate | spline_vs_additive | -0.00007 | [-0.00026765726338506585, 0.00012700076533559687] | 4/7 |
| driveKillerRate | additive_vs_offense | +0.00108 | [0.0007618642251608186, 0.0014240680412929518] | 11/0 |
| driveKillerRate | additive_vs_defense | +0.00133 | [0.001014056659498681, 0.0016761475653588244] | 11/0 |
| driveKillerRate | additive_vs_mean | +0.00224 | [0.0018148225138062437, 0.002720845623024235] | 11/0 |
| driveKillerRate | interaction_vs_additive | -0.00010 | [-0.00023343082211795392, 2.8463639772581207e-05] | 1/10 |
| driveKillerRate | boosting_vs_additive | -0.00120 | [-0.0016453204024583527, -0.000782660095545699] | 0/11 |
| driveKillerRate | spline_vs_additive | -0.00019 | [-0.00045319980217851496, 7.07527102105463e-05] | 5/6 |
| explosiveDependency | additive_vs_offense | +0.00062 | [0.00045409177173949804, 0.0007875862636354005] | 10/1 |
| explosiveDependency | additive_vs_defense | +0.00108 | [0.0008647657563665278, 0.0013201970091130746] | 11/0 |
| explosiveDependency | additive_vs_mean | +0.00177 | [0.0014812301468836234, 0.0020640444828971833] | 11/0 |
| explosiveDependency | interaction_vs_additive | -0.00011 | [-0.00022750269760364833, -2.787018553612525e-05] | 3/8 |
| explosiveDependency | boosting_vs_additive | -0.00082 | [-0.0011136441339347411, -0.000520082394881343] | 0/11 |
| explosiveDependency | spline_vs_additive | -0.00006 | [-0.0002233408052523423, 8.835253245559876e-05] | 5/6 |
| explosivePlayRate | additive_vs_offense | +0.00073 | [0.0006190456668244415, 0.0008399055756895892] | 11/0 |
| explosivePlayRate | additive_vs_defense | +0.00053 | [0.00044269604974104447, 0.00062399294300717] | 11/0 |
| explosivePlayRate | additive_vs_mean | +0.00124 | [0.0010935112536762065, 0.0014030823068268794] | 11/0 |
| explosivePlayRate | interaction_vs_additive | -0.00002 | [-3.937324215355216e-05, 6.017867240975042e-06] | 5/6 |
| explosivePlayRate | boosting_vs_additive | -0.00022 | [-0.00031677930878383015, -0.00011818882769589931] | 0/11 |
| explosivePlayRate | spline_vs_additive | +0.00005 | [-9.091469929918468e-06, 0.0001098108607784129] | 8/3 |
| failureBurden | additive_vs_offense | +0.00108 | [0.0008915271663029932, 0.0012714662853601066] | 11/0 |
| failureBurden | additive_vs_defense | +0.00139 | [0.0012294763582428694, 0.0015639030832421195] | 11/0 |
| failureBurden | additive_vs_mean | +0.00231 | [0.0020775135478395615, 0.0025497399938691325] | 11/0 |
| failureBurden | interaction_vs_additive | -0.00001 | [-3.9936388447490033e-05, 1.4257962080032444e-05] | 5/6 |
| failureBurden | boosting_vs_additive | -0.00057 | [-0.0008047601170254361, -0.00034737780743654954] | 0/11 |
| failureBurden | spline_vs_additive | +0.00002 | [-0.00010388443270477171, 0.0001442176465358795] | 6/5 |

### Nonlinear model decision

Retain additive models unless a nonlinear alternative reduces MAE by at least 1% relative to additive, its paired improvement interval excludes zero, and it improves at least seven seasons. This is a conservative practical threshold for this research pass, not a production promotion rule.

- cleanDriveRate: retain additive; neither nonlinear model clears all three checks.
- driveKillerRate: retain additive; neither nonlinear model clears all three checks.
- explosiveDependency: retain additive; neither nonlinear model clears all three checks.
- explosivePlayRate: retain additive; neither nonlinear model clears all three checks.
- failureBurden: retain additive; neither nonlinear model clears all three checks.

### Matchup buckets

Terciles are defined from each training fold, not the full season. Entries below show actual held-out target means (sample size) for the nine low/middle/high offense × opponent-defense combinations. Defense buckets use raw metric values: high Clean Drive Allowed and high explosive rate allowed mean weaker suppression, while high Drive Killer Forced and Failure Pressure mean stronger disruption.

| Target | Offense tercile | Defense low | Defense middle | Defense high |
|---|---|---|---|---|
| cleanDriveRate | low | 0.3563 (1,087) | 0.3760 (1,549) | 0.4042 (1,125) |
| cleanDriveRate | middle | 0.3737 (1,710) | 0.3964 (2,473) | 0.4297 (1,721) |
| cleanDriveRate | high | 0.4007 (1,204) | 0.4249 (1,870) | 0.4447 (1,126) |
| driveKillerRate | low | 0.7342 (1,174) | 0.7498 (1,720) | 0.7751 (1,285) |
| driveKillerRate | middle | 0.7572 (1,557) | 0.7875 (2,008) | 0.8079 (1,443) |
| driveKillerRate | high | 0.7797 (1,157) | 0.8089 (1,364) | 0.8402 (942) |
| explosiveDependency | low | 0.3904 (875) | 0.4151 (1,544) | 0.4380 (1,160) |
| explosiveDependency | middle | 0.4181 (1,534) | 0.4393 (2,598) | 0.4626 (1,925) |
| explosiveDependency | high | 0.4519 (1,106) | 0.4671 (1,871) | 0.4904 (1,364) |
| explosivePlayRate | low | 0.0970 (876) | 0.1096 (1,543) | 0.1219 (1,162) |
| explosivePlayRate | middle | 0.1071 (1,536) | 0.1202 (2,596) | 0.1344 (1,926) |
| explosivePlayRate | high | 0.1194 (1,107) | 0.1309 (1,872) | 0.1455 (1,365) |
| failureBurden | low | 0.3365 (979) | 0.3562 (1,804) | 0.3785 (1,366) |
| failureBurden | middle | 0.3604 (1,593) | 0.3801 (2,515) | 0.4024 (1,709) |
| failureBurden | high | 0.3826 (1,181) | 0.4011 (1,702) | 0.4209 (1,129) |

## Metric assessments

### Clean Drive Rate — MATCHUP SIGNAL

Share of eligible validated possessions without a tracked turnover, sack, TFL, costly accepted offensive penalty, or failed fourth down. A self-recovered fumble does not disqualify the drive.

- **2025 sample:** 1,616 materialized team-games; denominator total 18,162.00, median 11.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.124; chronological half-season Pearson 0.275, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: failureBurden -0.389, nonExplosiveEpaPerPlay 0.276, longDownAvoidanceRate 0.276. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0264; log-loss Δ +0.00154; accuracy Δ -0.072 pp. MAE improvement CI [-0.06201593096735296, 0.0023206071084091763]; accuracy improvement CI (fraction) [-0.004818799325522372, 0.0033530961789240005].
- **Season consistency:** MAE better/worse in 4/7 seasons (median improvement -0.0178 points); accuracy better/worse in 4/7 (median improvement -0.324 pp).
- **Matchup target:** see cleanDriveRate above; additive-vs-offense MAE improvement +0.00078, CI [0.0005265663573304537, 0.0010160733491107968].
- **Downstream:** epaPerPlay: 0.361, successRate: 0.262, pointsPerPossession: 0.347, points: 0.368, margin: 0.314. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

### Clean Drive Rate Allowed — MATCHUP SIGNAL

Opponent Clean Drive Rate against this defense; lower is better.

- **2025 sample:** 1,616 materialized team-games; denominator total 18,162.00, median 11.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.134; chronological half-season Pearson 0.305, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: failurePressure -0.389, longDownCreationRate -0.276, seriesStopRate -0.213. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0343; log-loss Δ +0.00225; accuracy Δ +0.158 pp. MAE improvement CI [-0.07484739661735831, 0.004684067022904601]; accuracy improvement CI (fraction) [-0.002380735870798837, 0.005449067285066329].
- **Season consistency:** MAE better/worse in 2/9 seasons (median improvement -0.0354 points); accuracy better/worse in 5/4 (median improvement +0.000 pp).
- **Matchup target:** see cleanDriveRate above; additive-vs-offense MAE improvement +0.00078, CI [0.0005265663573304537, 0.0010160733491107968].
- **Downstream:** epaPerPlay: 0.361, successRate: 0.262, pointsPerPossession: 0.347, points: 0.368, margin: 0.314. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

### Drive Killer Rate — MATCHUP SIGNAL

Among drives with a tracked mistake, the share whose final mistake is never followed by another first down or touchdown. Lower is better; the denominator is mistake-containing drives, not all drives.

- **2025 sample:** 1,616 materialized team-games; denominator total 11,179.00, median 7.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.129; chronological half-season Pearson 0.304, across 1,437 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: recoveryRate -0.558, seriesConversionRate -0.556, nonExplosiveEpaPerPlay -0.441. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0118; log-loss Δ +0.00722; accuracy Δ -0.519 pp. MAE improvement CI [-0.0697577048570899, 0.04016572440903006]; accuracy improvement CI (fraction) [-0.009945847831974842, -0.0009348670682481242].
- **Season consistency:** MAE better/worse in 7/4 seasons (median improvement +0.0308 points); accuracy better/worse in 3/8 (median improvement -0.349 pp).
- **Matchup target:** see driveKillerRate above; additive-vs-offense MAE improvement +0.00108, CI [0.0007618642251608186, 0.0014240680412929518].
- **Downstream:** epaPerPlay: -0.557, successRate: -0.425, pointsPerPossession: -0.590, points: -0.516, margin: -0.425. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

### Drive Killer Rate Forced — MATCHUP SIGNAL

Opponent Drive Killer Rate against this defense; higher is better. This measures finishing off mistake-containing drives, not how frequently the defense creates a mistake.

- **2025 sample:** 1,616 materialized team-games; denominator total 11,179.00, median 7.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.114; chronological half-season Pearson 0.230, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: closeoutRate 0.558, seriesStopRate 0.556, failurePressure 0.402. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0237; log-loss Δ +0.00367; accuracy Δ -0.424 pp. MAE improvement CI [-0.06805654750284315, 0.01563632701153399]; accuracy improvement CI (fraction) [-0.009104517611969582, 0.0003101749000535383].
- **Season consistency:** MAE better/worse in 4/7 seasons (median improvement -0.0209 points); accuracy better/worse in 4/7 (median improvement -0.527 pp).
- **Matchup target:** see driveKillerRate above; additive-vs-offense MAE improvement +0.00108, CI [0.0007618642251608186, 0.0014240680412929518].
- **Downstream:** epaPerPlay: -0.557, successRate: -0.425, pointsPerPossession: -0.590, points: -0.516, margin: -0.425. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

### Explosive Dependency — MATCHUP SIGNAL

Positive EPA from explosive plays divided by all positive EPA. Rush gains of 10+ yards and pass gains of 20+ yards are explosive. High dependency has no inherent good/bad direction.

- **2025 sample:** 1,616 materialized team-games; denominator total 56,305.36, median 34.9. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.134; chronological half-season Pearson 0.324, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: nonExplosiveEpaPerPlay -0.339, cleanDriveRate 0.113, driveKillerRate -0.102. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0246; log-loss Δ +0.00102; accuracy Δ -0.114 pp. MAE improvement CI [-0.04955113021193996, -0.0015734077030550317]; accuracy improvement CI (fraction) [-0.004397740912566071, 0.0023305091017818704].
- **Season consistency:** MAE better/worse in 3/8 seasons (median improvement -0.0079 points); accuracy better/worse in 5/6 (median improvement -0.144 pp).
- **Matchup target:** see explosiveDependency above; additive-vs-offense MAE improvement +0.00062, CI [0.00045409177173949804, 0.0007875862636354005].
- **Downstream:** epaPerPlay: 0.323, successRate: 0.038, pointsPerPossession: 0.247, points: 0.292, margin: 0.220. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

### Non-Explosive EPA/play — DESCRIPTIVE

EPA per non-explosive, EPA-eligible play. It is distinct from overall EPA/play despite strong correlation.

- **2025 sample:** 1,616 materialized team-games; denominator total 90,764.00, median 56.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.237; chronological half-season Pearson 0.435, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: seriesConversionRate 0.736, recoveryRate 0.655, failureBurden -0.634. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0178; log-loss Δ +0.00159; accuracy Δ +0.057 pp. MAE improvement CI [-0.049197461702622444, 0.008685158575967133]; accuracy improvement CI (fraction) [-0.0030289532588399326, 0.0038844456763245053].
- **Season consistency:** MAE better/worse in 4/7 seasons (median improvement -0.0244 points); accuracy better/worse in 6/5 (median improvement +0.160 pp).
- **Matchup target:** no natural defensive counterpart tested for this companion metric; evaluated individually and in grouped models.
- **Downstream:** epaPerPlay: 0.696, successRate: 0.768, pointsPerPossession: 0.651, points: 0.556, margin: 0.445. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

For generic win/margin prediction: descriptive / redundant-for-prediction in the tested feature sets; not a literal duplicate and retained on Exploratory.

### Failure Burden — MATCHUP SIGNAL

Sum of negative EPA magnitudes divided by EPA-eligible plays; lower is better.

- **2025 sample:** 1,616 materialized team-games; denominator total 105,135.00, median 65.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.178; chronological half-season Pearson 0.370, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: nonExplosiveEpaPerPlay -0.634, seriesConversionRate -0.525, recoveryRate -0.423. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0416; log-loss Δ +0.00181; accuracy Δ -0.043 pp. MAE improvement CI [-0.08422023999840664, -0.006032703776065757]; accuracy improvement CI (fraction) [-0.003952581590280787, 0.0027637914606697873].
- **Season consistency:** MAE better/worse in 2/9 seasons (median improvement -0.0225 points); accuracy better/worse in 7/4 (median improvement +0.152 pp).
- **Matchup target:** see failureBurden above; additive-vs-offense MAE improvement +0.00108, CI [0.0008915271663029932, 0.0012714662853601066].
- **Downstream:** epaPerPlay: -0.746, successRate: -0.555, pointsPerPossession: -0.599, points: -0.529, margin: -0.518. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

### Failure Pressure — MATCHUP SIGNAL

Opponent negative EPA magnitude per EPA-eligible play against the defense; higher is better.

- **2025 sample:** 1,616 materialized team-games; denominator total 105,135.00, median 65.0. FBS-vs-FBS research subset: 1,616 team-games.
- **Stability:** pregame-to-next-game Pearson 0.161; chronological half-season Pearson 0.359, across 1,438 team-seasons with at least three games in each half.
- **Redundancy:** strongest same-game correlations: seriesStopRate 0.525, closeoutRate 0.423, longDownCreationRate 0.416. Correlation does not establish literal duplication.
- **Generic prediction:** MAE Δ +0.0162; log-loss Δ +0.00129; accuracy Δ -0.356 pp. MAE improvement CI [-0.048021673600956986, 0.01865035399308446]; accuracy improvement CI (fraction) [-0.007692727272727273, 0.00028703811215994706].
- **Season consistency:** MAE better/worse in 4/7 seasons (median improvement -0.0083 points); accuracy better/worse in 2/7 (median improvement -0.318 pp).
- **Matchup target:** see failureBurden above; additive-vs-offense MAE improvement +0.00108, CI [0.0008915271663029932, 0.0012714662853601066].
- **Downstream:** epaPerPlay: -0.746, successRate: -0.555, pointsPerPossession: -0.600, points: -0.529, margin: -0.518. Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.
- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.

For generic win/margin prediction: descriptive / redundant-for-prediction in the tested feature sets; not a literal duplicate and retained on Exploratory.

## Corpus checks

Counter/range/mirror violations: 2; mirror comparisons: 57,762. Missing drive rows in the rating input: 85; rating nonconvergences: 0. These are aggregate sanity checks, supplemented by the metric implementation tests; they do not replace manual adjudication of every raw play.

### Isolated 2024 source anomaly

Game 401645328 (Army–Rice) has no opponent identifier on either materialized Exploratory row and no Failure Pressure counters. The canonical EPA data attribute 118 eligible plays to Rice and zero to Army, so this is also a source-attribution concern. The research preserves the historical baseline input rather than repairing production data during a research run. `without2024Sensitivity` re-scores the other ten seasons, whose per-season fitting cannot be affected by that game. Missing fields are excluded from target evaluation and do not add observations to cumulative counters. This is a localized data-quality limitation, not evidence that the metric definition is meaningless.

## Reproduction and artifacts

```sh
.venv/bin/python -m cfb_analytics.analytics.exploratory_wave2_research
.venv/bin/python -m cfb_analytics.analytics.exploratory_wave2_report
.venv/bin/python -m pytest -q
```

`report.json` contains complete model metrics, per-season accuracy/log loss/Brier/MAE/RMSE/Pearson/R², consistency, intervals, fold-defined bucket outcomes, sample checks, and sensitivity controls. Raw snapshots and individual predictions are stored locally in ignored gzip files because they contain premium game data. Use `--rebuild` on the research command after source-data or feature-construction changes; cached snapshots are not automatically content-invalidated.

## Ablation

Not triggered: the combined feature model did not improve aggregate MAE, log loss, Brier, or accuracy versus the historical baseline. This follows the requested conditional ablation rule.

## Sensitivity excluding 2024

| Model | Games | Δ MAE | Δ log loss | Δ accuracy pp |
|---|---:|---:|---:|---:|
| cleanDrive_additive | 6,309 | +0.0685 | +0.00397 | -0.111 |
| driveKiller_additive | 5,753 | +0.0518 | +0.00839 | -0.574 |
| failure_additive | 6,369 | +0.0403 | +0.00293 | -0.393 |
| explosive_additive | 6,368 | +0.0365 | +0.00092 | +0.016 |
| tier1 | 6,314 | -0.0533 | +0.00270 | +0.317 |
| wave2 | 5,753 | +0.1463 | +0.02208 | -0.608 |
| combined | 5,753 | +0.1160 | +0.03582 | -0.713 |
