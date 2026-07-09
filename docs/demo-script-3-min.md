# SecureScope 3-Minute Demo Script

**Target:** AMD Hackathon Track 3 (Unicorn Track)

## 0:00–0:20 | Opening
"Hello judges, we are presenting SecureScope for the Track 3 Unicorn Track. SecureScope is an AI Proof-of-Risk Digital Twin platform for authorized security validation. Our mission is to prove real business risk without ever putting production environments in danger."

## 0:20–0:45 | Problem
"Security teams are drowning in vulnerability reports. But those reports don't answer the real questions: Is this actually exploitable? What is the real business risk? And most importantly, how can we prove this risk to developers without attacking our live production servers?"

## 0:45–1:15 | Product Workflow
"SecureScope changes the paradigm. We take safe execution evidence, thoroughly redact any sensitive data, and pass it to our hybrid AI engine. The engine builds an attack surface graph, creates a digital twin scenario, and then runs a sandbox-only exploit simulation. Finally, an AI tribunal analyzes the results and produces a clear remediation and retest plan."

## 1:15–2:20 | Live Demo
"Let's see it in action. We've built this as a fully containerized submission.
*(Show terminal)*
I'll run our docker compose stack... and open the frontend command center.
*(Show frontend)*
Here is our AI Proof-of-Risk tab. Notice there is no raw evidence input and no target URL input—this is production-safe validation. We only use sanitized execution evidence from the backend.
I'll hit 'Run Analysis'.
*(Scroll through results)*
First, you see the routing trace. Then, the attack graph visualizing the threats. Here is the digital twin scenario, and below it, the results of the sandbox-only exploit simulation. Finally, we have the remediation steps and retest instructions."

## 2:20–2:45 | AMD Platform Usage
"What powers this? The live demo uses Fireworks/Gemma for deep reasoning. SecureScope also ships with an AMD ROCm-compatible local provider and compose profile so the same routing layer can run on AMD Developer Cloud once access is available. Right now, the local route is served by a deterministic mock for demo purposes. If any provider is down, we have a deterministic fallback for guaranteed safety."

## 2:45–3:00 | Closing
"In short, SecureScope delivers faster triage, safer proofs, and better remediation. It's a complete, containerized product ready for modern DevSecOps pipelines. Thank you for checking out SecureScope!"
