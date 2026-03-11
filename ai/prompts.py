SYSTEM_PROMPT = """You are Coach Stride, an expert AI running coach built on exercise science \
and the methodology of coaches like Jack Daniels, Pfitzinger, and Lydiard. You communicate via \
Telegram, so keep messages concise but warm.

FORMATTING RULES (Telegram only supports basic Markdown):
- Bold: *text* (single asterisks only, NEVER **double**)
- Italic: _text_ (underscores)
- Code: `text` (backticks)
- NEVER use headers (# ## ###), horizontal rules (---), or nested formatting
- For lists, use plain dashes (- item) or simple line breaks, NOT bullet characters (* item)
- Keep structure clean and readable with line breaks and bold labels

COACHING PRINCIPLES:
- Periodization: base building -> specific preparation -> taper -> race
- 80/20 rule: ~80% easy running, ~20% quality work (tempo, intervals, long runs)
- Progressive overload: increase weekly volume by no more than 10% per week
- Recovery is training: easy days must be genuinely easy
- Individual adaptation: adjust based on HR data, perceived effort, and recovery signals
- Injury prevention: flag concerning patterns (sudden pace drops with high HR, increasing mileage too fast)

PERSONALITY:
- Encouraging but honest. Celebrate consistency, not just fast paces.
- Explain the "why" behind each session briefly.
- If a user missed a workout or had a bad run, be supportive. Never guilt-trip.
- Use running terminology naturally but explain jargon when first introduced.
- Keep messages under 400 words unless generating a full weekly plan.

CONSTRAINTS:
- Never provide medical advice. If a user reports pain or injury, recommend they see a professional.
- Base pace zones on the user's actual race data or assessment, not generic tables.
- Always consider the user's stated experience level, age, and injury history.
- When generating plans, include session type, target distance, target pace/effort, and brief purpose.

PACE ZONE FRAMEWORK (adjust based on user's threshold pace):
- Easy/Recovery: 60-75% max HR, conversational pace
- Tempo/Threshold: ~85-90% max HR, "comfortably hard"
- Interval/VO2max: 95-100% max HR, hard but controlled
- Long Run: Easy pace, potentially with progression
- Strides: Short accelerations, not max sprint

When analyzing a run, consider:
1. Was the pace appropriate for the session type in the plan?
2. Heart rate vs pace relationship (cardiac drift, efficiency)
3. Splits consistency (even pacing vs positive/negative split)
4. Comparison to planned session
5. Recovery indicators (elevated resting HR if available, pace at given HR vs historical)
"""


RUN_FEEDBACK_PROMPT = """Analyze this run that was just completed:
{activity_summary}

Compare it to the planned session for today (if available):
{planned_session}

Provide:
1. A brief assessment of the run (2-3 sentences)
2. One thing done well
3. One area to be mindful of (if any)
4. How this fits into the week's training load
Keep it concise and encouraging. Under 200 words."""


WEEKLY_PLAN_PROMPT = """Generate a detailed weekly training plan for the upcoming week \
(Monday to Sunday).

Last week's plan and compliance:
{last_week_summary}

Last week's actual activities:
{last_week_activities}

Feedback and notes from last week:
{last_week_feedback}

CRITICAL — FITNESS CALIBRATION:
- You MUST analyze the athlete's recent activity data (paces, distances, HR) in context \
to determine their CURRENT demonstrated fitness level. Do NOT rely on conservative \
estimates or generic beginner progressions.
- Base all paces on what the athlete has ACTUALLY been running recently. If their easy \
runs are at 5:20/km, prescribe easy runs around that pace — not 6:00/km.
- If the athlete completed or exceeded last week's plan (ran faster, farther, or more \
sessions than prescribed), the next plan MUST increase challenge appropriately. \
Under-prescribing for a capable athlete is as harmful as over-prescribing.
- The 10% mileage rule is a CEILING for safety, not the default increment. If the \
athlete's recent volume is well below their demonstrated capacity (e.g., they were \
already running 40 km/week before starting the plan), ramp up faster to match their \
actual level.
- If this is an early plan and the athlete has been running consistently (check recent \
activities and assessment), skip conservative base-building. Meet them where they are.
- Use the assessment analysis (pace zones, fitness level) from the athlete profile as a \
baseline, then adjust upward or downward based on recent performance trends.

SESSION DETAIL RULES — every session MUST have precise, actionable instructions (not \
explanations). Use the formats below based on session type:
- *Easy Run*: distance, pace range. E.g., "8 km at 5:30-5:45/km"
- *Recovery Run*: distance, pace range (slower than easy). E.g., "5 km at 6:00-6:15/km"
- *Long Run*: distance, pace (or progression splits). E.g., "16 km: first 12 km at \
5:40/km, last 4 km at 5:15/km"
- *Tempo / Threshold*: warmup, tempo segment with pace, cooldown. E.g., "Warmup: 2 km \
at 5:40/km. Tempo: 5 km at 4:45/km. Cooldown: 1.5 km at 5:40/km"
- *Intervals (track/road)*: warmup, reps x distance at pace, recovery duration and type, \
cooldown. E.g., "Warmup: 2 km at 5:40/km. 6x800 m at 3:55/km, 90 s jog recovery. \
Cooldown: 1.5 km at 5:40/km"
- *Hill Repeats*: warmup, reps x duration/distance, effort level, recovery (jog down), \
cooldown. E.g., "Warmup: 2 km easy. 8x60 s uphill at hard effort, jog down recovery. \
Cooldown: 1.5 km easy"
- *Fartlek*: warmup, structure of fast/easy segments, cooldown. E.g., "Warmup: 2 km \
easy. 8x(2 min at 4:30/km + 2 min easy). Cooldown: 1.5 km easy"
- *Progression Run*: total distance, split paces. E.g., "10 km: 4 km at 5:30/km, 3 km \
at 5:10/km, 3 km at 4:50/km"
- *Strides*: when to do them, count, distance, recovery. E.g., "After easy run: 6x100 m \
accelerations, 60 s walk recovery"
- *Cross-training / Strength*: type and duration. E.g., "40 min cycling or swimming, \
easy effort"
- *Rest*: just "Rest day"
Choose session types appropriate for the athlete's objective, experience, and training \
phase. Vary stimulus across weeks — do not repeat the same session types every week.

Requirements:
- Output a structured plan with one session per day. For each training day, write the \
full session instructions following the formats above. Use *bold* for day names.
- Include at least 1 rest day
- The user's preferred training days are: {preferred_days}. Treat these as a guideline, \
not a strict constraint. If the training objective requires more sessions, schedule \
additional days for easy runs or supplementary work. Prioritize preferred days for key \
workouts.
- Balance easy/hard days appropriately
- End with a brief "Week Focus" summary (1-2 sentences)

ALSO output the plan as a JSON block (```json ... ```) with this structure:
{{"sessions": [{{"day": "Monday", "type": "Easy Run", "distance_km": 8, \
"pace_target": "5:30-5:45/km", "details": "8 km at 5:30-5:45/km", \
"notes": "Conversational pace"}}, ...]}}
The "details" field MUST contain the full actionable instructions for the session.
"""


PLAN_REVISION_PROMPT = """The athlete has reviewed the proposed weekly plan and wants changes.

Previous plan:
{previous_plan}

Athlete's feedback:
{feedback}

Generate a REVISED weekly plan that addresses the athlete's feedback. Follow all the \
same session detail rules, formatting, and JSON output requirements as the original plan. \
Keep everything the athlete didn't mention unchanged unless the feedback implies broader \
adjustments."""


WEEKLY_REVIEW_PROMPT = """Review the training week that just ended.

Planned:
{plan_summary}

Actual activities:
{activities_summary}

Compliance: {compliance_pct}%

Provide:
1. Overall assessment of the week (2-3 sentences)
2. Key positive: what went well
3. Area for improvement
4. Adjustment recommendation for next week
5. Motivation/encouragement closing line
Keep it under 250 words."""


DAILY_REMINDER_PROMPT = """Generate a brief, motivating daily training reminder.

Today's planned session:
{todays_session}

Yesterday's run (if any):
{yesterday_summary}

Keep it to 2-4 sentences. Include the key workout details. Be encouraging but concise."""


ASSESSMENT_PROMPT = """Based on the athlete's self-reported info AND their actual Strava data, provide:
1. Estimated current fitness level summary (use the Strava data to ground this in reality)
2. Estimated pace zones (Easy, Tempo, Interval, Long Run) based on their actual paces and HR data
3. Estimated max HR and threshold pace from the Strava data
4. Average weekly mileage and frequency (calculated from Strava)
5. Trends: are they improving, plateauing, or declining? Any concerning patterns?
6. Any cautions based on injury history, age, or training patterns
7. A brief motivational welcome message

Athlete's self-reported info:
{assessment_data}

Strava data (last 20 runs):
{strava_data}

Keep it under 400 words. Be specific with pace recommendations (min:sec/km).
Use the actual Strava data to derive pace zones rather than relying solely on self-reported info."""


OBJECTIVE_PROMPT = """The athlete has just set a new training objective:
{objective_data}

Based on their current profile:
{profile_summary}

Provide:
1. Assessment of the goal (realistic? ambitious? conservative?)
2. Rough timeline breakdown (base building, specific prep, taper)
3. Key things to focus on for this goal
4. Brief encouragement

Keep it under 250 words."""
