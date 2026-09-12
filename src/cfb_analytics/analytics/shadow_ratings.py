"""Validated opponent-adjusted rating solver.

The live publication wrapper in ``analytics.rating_model`` pins the reviewed
configuration and calls this implementation directly. Legacy delegates to the
unchanged production solver. The hierarchical model solves weighted normal
equations by dependency-free cyclic coordinate descent. Input definitions are
explicit and are not rewritten by the solver.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any

from .iterative_ratings import fit_metric_ratings as legacy_fit

COMPOSITE_SPECS = (
    ("EPA", "epaSum", "epaPlays"),
    ("Success", "successfulPlays", "successEligiblePlays"),
    ("Explosiveness", "successfulPlayYards", "successfulPlays"),
)
COMPOSITE_WEIGHTS = (6.8693, 1.7265, -0.1906)
COMPOSITE_VERSION = "epa-success-successful-yards-zpop-v1"
MODEL_VERSION = "hierarchical-hfa-shadow-v1"
SEASON_SCOPE = "current-season-only"
USES_PRIOR_SEASON_TEAM_STRENGTH = False
USES_PRESEASON_TEAM_PRIOR = False


class ConvergenceError(RuntimeError):
    """A failed fit must never be used as a rating snapshot."""


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_rows(rows: list[dict], season: int) -> dict[str, str]:
    """Validate metadata before excluding metric-ineligible observations."""
    groups: dict[str, str] = {}
    games: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    for row in rows:
        if row.get("season") != season:
            raise ValueError("Mixed or missing season in rating input")
        if row.get("classification") != "fbs" or row.get("opponent_classification") != "fbs":
            raise ValueError("Shadow ratings require explicitly classified FBS-vs-FBS rows")
        for key, conf_key in (("team", "conference"), ("opponent", "opponent_conference")):
            team, conf = row.get(key), row.get(conf_key)
            if not isinstance(team, str) or not team or not isinstance(conf, str) or not conf.strip():
                raise ValueError("Missing team or season-specific conference mapping")
            if team in groups and groups[team] != conf:
                raise ValueError(f"Conflicting conference mapping for {team} in {season}")
            groups[team] = conf
        if not isinstance(row.get("neutral_site"), bool) or row.get("home_away") not in ("home", "away"):
            raise ValueError("Missing or invalid canonical site metadata")
        gid = str(row.get("gameId") or row.get("game_id") or "")
        if not gid or (gid, row['team']) in seen:
            raise ValueError("Missing game ID or duplicate team-game row")
        seen.add((gid, row['team']))
        games[gid].append(row)
    for gid, pair in games.items():
        if len(pair) != 2:
            raise ValueError(f"Game {gid} must have two team rows")
        a, b = pair
        if a['team'] != b['opponent'] or b['team'] != a['opponent']:
            raise ValueError(f"Game {gid} has conflicting opponents")
        if a['neutral_site'] != b['neutral_site'] or {a['home_away'], b['home_away']} != {'home', 'away'}:
            raise ValueError(f"Game {gid} has conflicting site indicators")
    return groups


def home_indicator(row: dict) -> float:
    if not isinstance(row.get("neutral_site"), bool) or row.get("home_away") not in ("home", "away"):
        raise ValueError("Invalid site metadata")
    return 0.0 if row["neutral_site"] else (1.0 if row["home_away"] == "home" else -1.0)


def model_metadata(rows, *, model_mode, season, cutoff, input_version, lambda_team, lambda_conf, hfa_enabled):
    if model_mode not in ("legacy", "hierarchical_hfa"):
        raise ValueError(f"Unknown model mode: {model_mode}")
    if not input_version or cutoff is None:
        raise ValueError("An explicit input version and cutoff are required")
    meta = dict(modelMode=model_mode,
                modelVersion=MODEL_VERSION if model_mode == 'hierarchical_hfa' else 'iterative-ratings-v2-directional',
                lambdaTeam=lambda_team, lambdaConference=lambda_conf,
                hfaEnabled=hfa_enabled, compositeVersion=COMPOSITE_VERSION,
                compositeWeights=list(COMPOSITE_WEIGHTS), season=season, cutoff=cutoff,
                inputVersion=input_version, shadowOnly=True)
    if model_mode == "hierarchical_hfa":
        # These fields are part of the semantic model identity. Changing a live
        # fit to use a prior-year/preseason team signal must therefore change
        # the model key instead of silently reusing the current model identity.
        meta.update(
            seasonScope=SEASON_SCOPE,
            usesPriorSeasonTeamStrength=USES_PRIOR_SEASON_TEAM_STRENGTH,
            usesPreseasonTeamPrior=USES_PRESEASON_TEAM_PRIOR,
        )
    # No shared legacy cache path; content+semantic configuration address every shadow fit.
    ordered = sorted(rows, key=lambda r: (str(r.get('gameId') or r.get('game_id')), str(r.get('team'))))
    source = json.dumps(ordered, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    meta['sourceHash'] = hashlib.sha256(source).hexdigest()
    meta['modelKey'] = hashlib.sha256(json.dumps(meta, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return meta


def fit_metric_ratings(rows, spec, *, model_mode, season, cutoff, input_version,
                       lambda_team=None, lambda_conf=400.0, hfa_enabled=True,
                       tolerance=1e-9, residual_tolerance=1e-10, max_iterations=10000):
    """Explicit shadow API; legacy numeric result remains byte-for-byte equivalent.

    `cutoff` documents the caller's selection, not an implicit filtering operation.
    Caller must supply only the observations available at that cutoff.
    """
    if model_mode not in ('legacy', 'hierarchical_hfa'):
        raise ValueError(f"Unknown model mode: {model_mode}")
    lt = float(lambda_team if lambda_team is not None else (50 if model_mode == 'legacy' else 200))
    if not finite(lt) or lt <= 0 or not finite(lambda_conf) or lambda_conf <= 0:
        raise ValueError("Penalties must be finite and positive")
    if not finite(tolerance) or tolerance <= 0 or not finite(residual_tolerance) or residual_tolerance <= 0 or max_iterations < 1:
        raise ValueError("Invalid convergence settings")
    meta = model_metadata(rows, model_mode=model_mode, season=season, cutoff=cutoff, input_version=input_version,
                          lambda_team=lt, lambda_conf=lambda_conf if model_mode != 'legacy' else None,
                          hfa_enabled=bool(hfa_enabled) if model_mode != 'legacy' else False)
    meta['metricSpec'] = list(spec)
    # Metric and solver settings also belong to the identity (never reuse another metric's fit).
    meta['solverSettings'] = {'tolerance': tolerance, 'residualTolerance': residual_tolerance, 'maxIterations': max_iterations} if model_mode != 'legacy' else {'tolerance': 1e-7, 'maxIterations': 2000, 'damping': 1.0}
    meta['modelKey'] = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()
    if model_mode == 'legacy':
        result = legacy_fit(rows, spec, shrinkage=lt)
        return {**result, 'modelMetadata': meta}
    groups = validate_rows(rows, season)
    teams, confs = sorted(groups), sorted(set(groups.values()))
    ti, ci = {t:i for i,t in enumerate(teams)}, {c:i for i,c in enumerate(confs)}
    T, C = len(teams), len(confs)
    size = 2 + 2*T + 2*C  # mu,h,a,b,A,B
    gram = [defaultdict(float) for _ in range(size)]
    rhs = [0.0]*size
    obs = []
    _, numerator, denominator = spec
    for row in rows:
        value, w = row.get(numerator), row.get(denominator)
        if not finite(value) or not finite(w) or w <= 0:
            continue
        t,o=ti[row['team']],ti[row['opponent']]
        h = home_indicator(row) if hfa_enabled else 0.0
        columns = [(0,1.0),(2+t,1.0),(2+T+o,-1.0),
                   (2+2*T+ci[groups[row['team']]],1.0),
                   (2+2*T+C+ci[groups[row['opponent']]],-1.0)]
        if h: columns.append((1,h))
        y = value/w
        obs.append((columns,w,y))
        for j,x in columns:
            rhs[j] += w*x*y
            for k,z in columns: gram[j][k] += w*x*z
    if not obs:
        raise ValueError(f"No eligible observations for {spec[0]}")
    hfa_available = bool(gram[1].get(1,0))
    if hfa_available and gram[1][1] - gram[0].get(1, 0)**2 / gram[0][0] <= 1e-12 * gram[0][0]:
        raise ValueError('HFA is unidentified: eligible observations have a constant site indicator')
    penalty = [0.0,0.0]+[lt]*(2*T)+[float(lambda_conf)]*(2*C)
    for j,pen in enumerate(penalty): gram[j][j] += pen
    active = [j for j in range(size) if j != 1 or hfa_available]
    diag = [gram[j].get(j,0) for j in range(size)]
    offdiag = [[(k,v) for k,v in row.items() if k != j] for j,row in enumerate(gram)]
    beta=[0.0]*size
    scale=max(1.0,max(abs(x) for x in rhs))
    for iteration in range(1,max_iterations+1):
        delta=0.0
        for j in active:
            new=(rhs[j]-sum(v*beta[k] for k,v in offdiag[j]))/diag[j]
            delta=max(delta,abs(new-beta[j]));beta[j]=new
        residual=max(abs(diag[j]*beta[j]+sum(v*beta[k] for k,v in offdiag[j])-rhs[j]) for j in active)/scale
        if delta<=tolerance and residual<=residual_tolerance: break
    else:
        raise ConvergenceError(f"{spec[0]} did not converge after {max_iterations} iterations: delta={delta:.3g}, scaled residual={residual:.3g}")
    if not all(math.isfinite(x) for x in beta):
        raise ConvergenceError("Non-finite rating solution")
    O={t:beta[2+i]+beta[2+2*T+ci[groups[t]]] for t,i in ti.items()}
    D={t:beta[2+T+i]+beta[2+2*T+C+ci[groups[t]]] for t,i in ti.items()}
    mo,md=sum(O.values())/T,sum(D.values())/T
    return dict(leagueMean=beta[0]+mo-md, hfa=beta[1], hfaAvailable=hfa_available,
                offense={t:v-mo for t,v in O.items()},defense={t:v-md for t,v in D.items()},
                conferenceOffense={c:beta[2+2*T+i] for c,i in ci.items()},
                conferenceDefense={c:beta[2+2*T+C+i] for c,i in ci.items()},
                centering={'offenseMean':mo,'defenseMean':md,'rawIntercept':beta[0]},
                iterations=iteration,converged=True,maxDelta=delta,scaledNormalResidual=residual,
                observations=len(obs),modelMetadata=meta)


def composite_from_fits(fits):
    """Neutral-field composite only; rejects mixed model/snapshot/input identities."""
    if set(fits) != {s[0] for s in COMPOSITE_SPECS}:
        raise ValueError("Composite requires exactly the three reviewed metrics")
    expected = None
    teams = None
    result = {}
    for metric, *_ in COMPOSITE_SPECS:
        f = fits[metric]
        meta = f['modelMetadata']
        identity_keys = [
            'modelMode','modelVersion','lambdaTeam','lambdaConference','hfaEnabled',
            'compositeVersion','compositeWeights','season','cutoff','inputVersion','sourceHash',
        ]
        if meta.get('modelMode') == 'hierarchical_hfa':
            identity_keys.extend(('seasonScope','usesPriorSeasonTeamStrength','usesPreseasonTeamPrior'))
        identity = {k:meta[k] for k in identity_keys}
        if expected is not None and expected != identity:
            raise ValueError("Mixed model/input/cutoff composite")
        expected = identity
        for side in ('offense','defense'):
            keys=set(f[side])
            if teams is not None and keys != teams:
                raise ValueError("Different metric team universes")
            teams=keys
    for side,label in [('offense','AdjOff'),('defense','AdjDef')]:
        combined={t:0.0 for t in sorted(teams)}
        for (metric,*_),weight in zip(COMPOSITE_SPECS,COMPOSITE_WEIGHTS):
            values=fits[metric][side];mean=sum(values.values())/len(values)
            sd=math.sqrt(sum((v-mean)**2 for v in values.values())/len(values)) or 1.0
            for t in combined: combined[t]+=weight*(values[t]-mean)/sd
        result[label]=combined
    result['AdjNet']={t:result['AdjOff'][t]+result['AdjDef'][t] for t in sorted(teams)}
    return result


def fit_composite(rows, **kwargs):
    fits={s[0]:fit_metric_ratings(rows,s,**kwargs) for s in COMPOSITE_SPECS}
    return {'fits':fits, 'ratings':composite_from_fits(fits)}
