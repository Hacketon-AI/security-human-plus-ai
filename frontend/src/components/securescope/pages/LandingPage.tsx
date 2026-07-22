"use client";

import * as React from "react";
import { useApp } from "@/lib/securescope/store";
import {
  Shield,
  Lock,
  Terminal,
  Activity,
  Cpu,
  CheckCircle2,
  Play,
  Pause,
  RefreshCw,
  ArrowRight,
  Globe,
  Zap,
  ChevronRight,
  LogIn,
  ShieldCheck,
  Crosshair,
  Radar,
  Flame,
  Check,
  Download,
  ShieldAlert,
  Sparkles,
  BarChart3,
} from "lucide-react";

interface LogEntry {
  id: string;
  time: string;
  level: "INFO" | "RECON" | "SCOPE" | "EXPLOIT" | "VULN" | "PROOF" | "SUCCESS";
  module: string;
  message: string;
}

interface NodeData {
  id: string;
  x: number;
  y: number;
  label: string;
  role: string;
  ip: string;
  latency: string;
  color: string;
  radius: number;
  packets: number;
  status: "ACTIVE" | "ENFORCED" | "SYNCED";
}

const PRESET_TARGETS = [
  {
    id: "pinjamanku",
    name: "Pinjamanku Lending API Gateway",
    domain: "api.staging.pinjamanku.co.id",
    type: "REST API / OAuth 2.0",
    riskTier: "High Controlled",
    status: "In Scope",
  },
  {
    id: "ojk-portal",
    name: "OJK Regulatory Reporting Portal",
    domain: "portal.compliance-ojk.gov.id",
    type: "Web Application / SSRF",
    riskTier: "Critical Validated",
    status: "In Scope",
  },
  {
    id: "sigma-cloud",
    name: "Telkom Sigma Cloud Control Plane",
    domain: "control-plane.sigma-cloud.net",
    type: "gRPC & Mesh Gateway",
    riskTier: "Moderate Tier-1",
    status: "In Scope",
  },
  {
    id: "internal-vault",
    name: "Vault Secrets Broker Node",
    domain: "vault.internal-mesh.io",
    type: "Identity Broker",
    riskTier: "High Controlled",
    status: "In Scope",
  },
];

const PEN_TEST_SCENARIOS = [
  {
    id: "jwt_bypassed",
    name: "JWT Signature Algorithm Confusion (RS256 → HS256)",
    category: "Authentication",
    risk: "Critical",
    description: "Testing token signature verification forgery by forcing symmetric secret evaluation.",
  },
  {
    id: "sqli_time",
    name: "Blind Time-Based SQL Injection on Search Endpoint",
    category: "Injection",
    risk: "High",
    description: "Measuring response latencies via non-destructive SLEEP(0.5) payloads.",
  },
  {
    id: "ssrf_cloud",
    name: "SSRF Cloud Metadata Credentials Extraction",
    category: "Server-Side Request",
    risk: "Critical",
    description: "Validating egress path isolation against 169.254.169.254 endpoint.",
  },
  {
    id: "idor_object",
    name: "IDOR Account Object Access Escalation",
    category: "Authorization",
    risk: "High",
    description: "Cross-tenant record enumeration with revoked operational tokens.",
  },
];

const ATTACK_PHASES = [
  { title: "SQLi Time-based Payload", detail: "SLEEP(0.5) -- Testing Target DB", risk: "CRITICAL", origin: "185.122.8.43" },
  { title: "JWT Algorithm Confusion", detail: "RS256 -> HS256 Signature Bypass", risk: "CRITICAL", origin: "103.14.22.10" },
  { title: "SSRF Cloud Metadata", detail: "169.254.169.254 Egress Isolation", risk: "HIGH", origin: "198.51.100.4" },
  { title: "IDOR Object Enumeration", detail: "Cross-Tenant User Profile Access", risk: "HIGH", origin: "45.33.22.11" },
];

export function LandingPage() {
  const go = useApp((state) => state.go);
  const authenticated = useApp((state) => state.authenticated);

  const [selectedTarget, setSelectedTarget] = React.useState(PRESET_TARGETS[0]);
  const [customDomain, setCustomDomain] = React.useState("");
  const [isScanning, setIsScanning] = React.useState(true);
  const [scanSpeed, setScanSpeed] = React.useState<1 | 2 | 5>(1);
  const [activeTab, setActiveTab] = React.useState<"terminal" | "topology" | "vectors">("topology");
  const [logs, setLogs] = React.useState<LogEntry[]>([]);
  const [activeVectorIndex, setActiveVectorIndex] = React.useState(0);

  // Stats state
  const [probesCount, setProbesCount] = React.useState(16480);
  const [vulnFound, setVulnFound] = React.useState(4);

  // Topology node selection
  const [selectedNode, setSelectedNode] = React.useState<NodeData | null>(null);

  // Hero Attack Simulation Canvas & Ticker
  const heroAttackCanvasRef = React.useRef<HTMLCanvasElement>(null);
  const [heroAttackPhase, setHeroAttackPhase] = React.useState(0);

  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const terminalRef = React.useRef<HTMLDivElement>(null);

  // Rotate hero attack vector phase every 3 seconds
  React.useEffect(() => {
    const timer = setInterval(() => {
      setHeroAttackPhase((prev) => (prev + 1) % ATTACK_PHASES.length);
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  // Hero Live Attack Simulation 60FPS Canvas Engine
  React.useEffect(() => {
    const canvas = heroAttackCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let frame = 0;

    const resize = () => {
      if (!canvas.parentElement) return;
      canvas.width = canvas.parentElement.clientWidth;
      canvas.height = 360;
    };
    resize();
    window.addEventListener("resize", resize);

    // Origin nodes matched to global world map coordinates
    const origins = [
      { x: 0.22, y: 0.38, label: "US-EAST NODE (185.122.8.43)", color: "#ef4444" },
      { x: 0.50, y: 0.32, label: "EU-CENTRAL NODE (103.14.22.10)", color: "#00f0ff" },
      { x: 0.82, y: 0.40, label: "ASIA-PACIFIC NODE (198.51.100.4)", color: "#8b5cf6" },
      { x: 0.32, y: 0.72, label: "SA-LATAM NODE (45.33.22.11)", color: "#f59e0b" },
    ];

    // Particles traveling from origins to central target
    const particles: { originIdx: number; progress: number; speed: number; size: number }[] = [];
    for (let i = 0; i < 28; i++) {
      particles.push({
        originIdx: i % origins.length,
        progress: Math.random(),
        speed: 0.005 + Math.random() * 0.007,
        size: 3 + Math.random() * 2.5,
      });
    }

    // Impact shockwaves at central node
    const impactRings: { radius: number; opacity: number; color: string }[] = [];

    const draw = () => {
      frame++;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width * 0.5;
      const cy = canvas.height * 0.5;

      // 1. Cyber Grid Overlay
      ctx.strokeStyle = "rgba(6, 182, 212, 0.09)";
      ctx.lineWidth = 1;
      const step = 32;
      for (let x = 0; x < canvas.width; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y < canvas.height; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // 2. Central Core Target Node
      const serverRadius = 24 + Math.sin(frame * 0.07) * 3;

      // Pulsing outer glow
      ctx.beginPath();
      ctx.arc(cx, cy, serverRadius + 12, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(239, 68, 68, 0.35)";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Core Server Fill
      ctx.beginPath();
      ctx.arc(cx, cy, serverRadius, 0, Math.PI * 2);
      ctx.fillStyle = "#030712";
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 2.5;
      ctx.fill();
      ctx.stroke();

      // Server Center Icon / Text
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 11px monospace";
      ctx.textAlign = "center";
      ctx.fillText("CORE TARGET", cx, cy - 3);
      ctx.fillStyle = "#ef4444";
      ctx.font = "9px monospace";
      ctx.fillText("[INJECTING]", cx, cy + 9);

      // 3. Draw Impact Shockwaves
      for (let i = impactRings.length - 1; i >= 0; i--) {
        const ring = impactRings[i];
        ring.radius += 1.8;
        ring.opacity -= 0.025;
        if (ring.opacity <= 0) {
          impactRings.splice(i, 1);
          continue;
        }
        ctx.beginPath();
        ctx.arc(cx, cy, ring.radius, 0, Math.PI * 2);
        ctx.strokeStyle = ring.color.replace("1)", `${ring.opacity})`);
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // 4. Draw Origin Nodes & Curved Laser Attack Beams
      origins.forEach((node, idx) => {
        const nx = node.x * canvas.width;
        const ny = node.y * canvas.height;

        const cpx = (nx + cx) / 2 + (idx % 2 === 0 ? 55 : -55);
        const cpy = (ny + cy) / 2 + (idx > 1 ? -45 : 45);

        // Curved Laser Beam Path
        ctx.beginPath();
        ctx.moveTo(nx, ny);
        ctx.quadraticCurveTo(cpx, cpy, cx, cy);
        ctx.strokeStyle = `${node.color}50`;
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Origin Node Circle
        ctx.beginPath();
        ctx.arc(nx, ny, 8, 0, Math.PI * 2);
        ctx.fillStyle = "#020617";
        ctx.strokeStyle = node.color;
        ctx.lineWidth = 2;
        ctx.fill();
        ctx.stroke();

        // Node Label
        ctx.font = "bold 9px monospace";
        ctx.fillStyle = "#cbd5e1";
        ctx.textAlign = idx < 2 ? "left" : "right";
        ctx.fillText(node.label, nx + (idx < 2 ? 14 : -14), ny + 3);
      });

      // 5. Draw Energy Packets Shooting Along Curves
      particles.forEach((p) => {
        p.progress += p.speed;
        if (p.progress >= 1) {
          p.progress = 0;
          // Spawn impact shockwave ring
          impactRings.push({
            radius: serverRadius,
            opacity: 0.85,
            color: origins[p.originIdx].color,
          });
        }

        const node = origins[p.originIdx];
        const nx = node.x * canvas.width;
        const ny = node.y * canvas.height;
        const cpx = (nx + cx) / 2 + (p.originIdx % 2 === 0 ? 55 : -55);
        const cpy = (ny + cy) / 2 + (p.originIdx > 1 ? -45 : 45);

        // Quadratic Bezier interpolation
        const t = p.progress;
        const px = Math.pow(1 - t, 2) * nx + 2 * (1 - t) * t * cpx + Math.pow(t, 2) * cx;
        const py = Math.pow(1 - t, 2) * ny + 2 * (1 - t) * t * cpy + Math.pow(t, 2) * cy;

        // Glowing energy pulse particle
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fillStyle = node.color;
        ctx.shadowColor = node.color;
        ctx.shadowBlur = 12;
        ctx.fill();
        ctx.shadowBlur = 0;
      });

      animId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animId);
    };
  }, []);

  // Radar Topology 2D Canvas Engine
  React.useEffect(() => {
    if (activeTab !== "topology") return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let angle = 0;

    const initialNodes: NodeData[] = [
      { id: "target", x: 0.5, y: 0.5, label: "TARGET GATEWAY", role: "Primary Asset Node", ip: "103.14.22.104", latency: "1.2ms", color: "#00f0ff", radius: 14, packets: 8490, status: "ACTIVE" },
      { id: "worker_sg", x: 0.22, y: 0.32, label: "WORKER-SG1", role: "Payload Probe Node", ip: "128.199.204.12", latency: "14ms", color: "#8b5cf6", radius: 9, packets: 3410, status: "ACTIVE" },
      { id: "worker_id", x: 0.78, y: 0.28, label: "WORKER-ID2", role: "Fuzzing Worker Node", ip: "103.147.33.88", latency: "6ms", color: "#8b5cf6", radius: 9, packets: 4120, status: "ACTIVE" },
      { id: "scope", x: 0.28, y: 0.72, label: "SCOPE GUARD", role: "CIDR Boundary Enforcer", ip: "10.0.0.1", latency: "0.4ms", color: "#10b981", radius: 10, packets: 12400, status: "ENFORCED" },
      { id: "ledger", x: 0.72, y: 0.72, label: "PROOF LEDGER", role: "SHA-256 Audit Storage", ip: "10.0.0.5", latency: "2.1ms", color: "#f59e0b", radius: 10, packets: 520, status: "SYNCED" },
      { id: "proxy", x: 0.12, y: 0.52, label: "WAF PROXY", role: "Traffic Inspection Relay", ip: "172.16.0.4", latency: "3.5ms", color: "#00f0ff", radius: 8, packets: 9810, status: "ACTIVE" },
      { id: "proofer", x: 0.88, y: 0.52, label: "AI PROOFER", role: "Evidence Verifier Engine", ip: "10.0.10.12", latency: "8.4ms", color: "#ec4899", radius: 8, packets: 1420, status: "ACTIVE" },
    ];

    if (!selectedNode) {
      setSelectedNode(initialNodes[0]);
    }

    const handleCanvasClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      initialNodes.forEach((node) => {
        const nx = node.x * canvas.width;
        const ny = node.y * canvas.height;
        const dist = Math.hypot(clickX - nx, clickY - ny);
        if (dist <= node.radius + 10) {
          setSelectedNode(node);
        }
      });
    };

    canvas.addEventListener("click", handleCanvasClick);

    const resize = () => {
      if (!canvas.parentElement) return;
      canvas.width = canvas.parentElement.clientWidth;
      canvas.height = 420;
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const maxRadius = Math.min(canvas.width, canvas.height) * 0.42;

      // 1. Grid Lines
      ctx.strokeStyle = "rgba(14, 116, 144, 0.12)";
      ctx.lineWidth = 1;
      const gridSize = 35;
      for (let x = 0; x < canvas.width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y < canvas.height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // 2. Concentric Radar Circles
      [0.25, 0.5, 0.75, 1.0].forEach((r) => {
        ctx.beginPath();
        ctx.arc(cx, cy, maxRadius * r, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(6, 182, 212, 0.22)";
        ctx.setLineDash([4, 6]);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Crosshair Axes
      ctx.strokeStyle = "rgba(6, 182, 212, 0.15)";
      ctx.beginPath();
      ctx.moveTo(cx, cy - maxRadius);
      ctx.lineTo(cx, cy + maxRadius);
      ctx.moveTo(cx - maxRadius, cy);
      ctx.lineTo(cx + maxRadius, cy);
      ctx.stroke();

      // 3. Rotating Radar Sweep Beam
      angle += (isScanning ? 0.018 : 0.003) * scanSpeed;
      if (angle > Math.PI * 2) angle = 0;

      const gradient = ctx.createConicGradient(angle, cx, cy);
      gradient.addColorStop(0, "rgba(6, 182, 212, 0.35)");
      gradient.addColorStop(0.18, "rgba(6, 182, 212, 0.06)");
      gradient.addColorStop(0.35, "rgba(6, 182, 212, 0)");
      gradient.addColorStop(1, "rgba(6, 182, 212, 0)");

      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cx, cy, maxRadius, 0, Math.PI * 2);
      ctx.fill();

      // Sweep Edge Line
      const lx = cx + Math.cos(angle) * maxRadius;
      const ly = cy + Math.sin(angle) * maxRadius;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(lx, ly);
      ctx.strokeStyle = "rgba(6, 182, 212, 0.9)";
      ctx.lineWidth = 2;
      ctx.stroke();

      // 4. Draw Node Connections & Animated Packets
      const targetNode = initialNodes[0];
      const targetX = targetNode.x * canvas.width;
      const targetY = targetNode.y * canvas.height;

      initialNodes.forEach((node, idx) => {
        if (idx === 0) return;
        const nx = node.x * canvas.width;
        const ny = node.y * canvas.height;

        ctx.beginPath();
        ctx.moveTo(targetX, targetY);
        ctx.lineTo(nx, ny);
        ctx.strokeStyle = `${node.color}40`;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Traveling Packet
        if (isScanning) {
          const time = Date.now() * 0.0018 * scanSpeed + idx;
          const progress = time % 1;
          const px = targetX + (nx - targetX) * progress;
          const py = targetY + (ny - targetY) * progress;

          ctx.beginPath();
          ctx.arc(px, py, 3.5, 0, Math.PI * 2);
          ctx.fillStyle = node.color;
          ctx.shadowColor = node.color;
          ctx.shadowBlur = 10;
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      });

      // 5. Render Nodes
      initialNodes.forEach((node, idx) => {
        const nx = node.x * canvas.width;
        const ny = node.y * canvas.height;
        const isSelected = selectedNode?.id === node.id;

        // Pulsing Ring
        const pulse = (Math.sin(Date.now() * 0.004 + idx) + 1) * 6;
        ctx.beginPath();
        ctx.arc(nx, ny, node.radius + pulse + (isSelected ? 4 : 0), 0, Math.PI * 2);
        ctx.strokeStyle = `${node.color}${isSelected ? "88" : "33"}`;
        ctx.lineWidth = isSelected ? 2 : 1.5;
        ctx.stroke();

        // Selection Target Ring
        if (isSelected) {
          ctx.beginPath();
          ctx.arc(nx, ny, node.radius + 12, 0, Math.PI * 2);
          ctx.strokeStyle = "#00f0ff";
          ctx.setLineDash([3, 3]);
          ctx.stroke();
          ctx.setLineDash([]);
        }

        // Inner Core
        ctx.beginPath();
        ctx.arc(nx, ny, node.radius, 0, Math.PI * 2);
        ctx.fillStyle = idx === 0 ? "#020617" : "#0f172a";
        ctx.strokeStyle = node.color;
        ctx.lineWidth = 2;
        ctx.fill();
        ctx.stroke();

        // Core Dot
        ctx.beginPath();
        ctx.arc(nx, ny, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = node.color;
        ctx.fill();

        // Label
        ctx.font = "bold 10px monospace";
        ctx.fillStyle = isSelected ? "#00f0ff" : "#94a3b8";
        ctx.textAlign = "center";
        ctx.fillText(node.label, nx, ny + node.radius + 14);
      });

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      canvas.removeEventListener("click", handleCanvasClick);
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, [activeTab, isScanning, scanSpeed, selectedNode]);

  // Terminal Log Stream Generator
  React.useEffect(() => {
    if (!isScanning) return;

    const targetDomain = customDomain.trim() || selectedTarget.domain;

    const logTemplates: { level: LogEntry["level"]; module: string; msg: string }[] = [
      { level: "SCOPE", module: "AUTH_CHECK", msg: `Validating target [${targetDomain}] CIDR & Ownership certificate...` },
      { level: "INFO", module: "SCOPE_GUARD", msg: `Cryptographic proof signature VERIFIED. Max Risk Tier: TIER-2 CONTROLLED.` },
      { level: "RECON", module: "NMAP_ENGINE", msg: `Enumerating ports 80, 443, 8080, 8443 on ${targetDomain}...` },
      { level: "INFO", module: "NMAP_ENGINE", msg: `Discovered HTTP/2 endpoints & TLS 1.3 Cipher Suites [TLS_AES_256_GCM_SHA384].` },
      { level: "RECON", module: "CRAWLER", msg: `Discovered API endpoint: POST /api/v2/auth/login` },
      { level: "RECON", module: "CRAWLER", msg: `Discovered API endpoint: GET /api/v2/user/profile?id=USR-9921` },
      { level: "EXPLOIT", module: "JWT_FUZZER", msg: `Injecting RS256 -> HS256 algorithm confusion payload into Authorization header...` },
      { level: "VULN", module: "PROOFER", msg: `[VULN DETECTED] Token accepted with null public key signature on /api/v2/auth/login!` },
      { level: "PROOF", module: "CRYPTO_EVIDENCE", msg: `Generating SHA-256 evidence snapshot #EVID-${Math.floor(Math.random() * 9000 + 1000)}.` },
      { level: "EXPLOIT", module: "SQLI_TESTER", msg: `Testing blind time-based injection: SLEEP(0.5) on query param 'id'...` },
      { level: "INFO", module: "SQLI_TESTER", msg: `Response latency baseline: 42ms. Payload latency: 541ms (3 iterations confirmed).` },
      { level: "VULN", module: "PROOFER", msg: `[VULN DETECTED] High probability SQL Injection verified on /api/v2/user/profile!` },
      { level: "EXPLOIT", module: "SSRF_GUARD", msg: `Testing outbound HTTP request callback against 169.254.169.254 metadata node...` },
      { level: "INFO", module: "SSRF_GUARD", msg: `Egress proxy blocked outbound metadata request. Zero leak verified.` },
      { level: "SUCCESS", module: "AUDIT_LEDGER", msg: `Validation run completed safely. Risk Tier: HIGH. Zero downtime recorded.` },
    ];

    let stepIndex = 0;
    const intervalTime = 1200 / scanSpeed;

    const interval = setInterval(() => {
      const template = logTemplates[stepIndex % logTemplates.length];
      const now = new Date();
      const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}.${now.getMilliseconds().toString().padStart(3, "0")}`;

      const newLog: LogEntry = {
        id: Math.random().toString(36).substring(2, 9),
        time: timeStr,
        level: template.level,
        message: template.msg.replace(/\${targetDomain}/g, targetDomain),
        module: template.module,
      };

      setLogs((prev) => [...prev.slice(-80), newLog]);
      setProbesCount((prev) => prev + Math.floor(Math.random() * 14 + 6));

      if (template.level === "VULN") {
        setVulnFound((prev) => prev + 1);
        setActiveVectorIndex((prev) => (prev + 1) % PEN_TEST_SCENARIOS.length);
      }

      stepIndex++;

      if (terminalRef.current) {
        terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
      }
    }, intervalTime);

    return () => clearInterval(interval);
  }, [isScanning, scanSpeed, selectedTarget, customDomain]);

  const handleStartCustomScan = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customDomain.trim()) return;
    setLogs([]);
    setIsScanning(true);
  };

  const handleDownloadEvidence = () => {
    const reportData = {
      system: "SecureScope Engine v2.4",
      target: customDomain.trim() || selectedTarget.domain,
      timestamp: new Date().toISOString(),
      probesExecuted: probesCount,
      vulnerabilitiesConfirmed: vulnFound,
      evidenceHash: "sha256:" + Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join(""),
      logs: logs.filter((l) => l.level === "VULN" || l.level === "PROOF"),
    };
    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `securescope-evidence-${selectedTarget.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-[#02050b] text-slate-100 font-sans selection:bg-cyan-500 selection:text-black overflow-x-hidden">
      {/* Background Radial Lights */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 left-1/4 w-[700px] h-[700px] bg-cyan-500/10 rounded-full blur-[160px] animate-pulse" />
        <div className="absolute bottom-10 right-1/4 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-[180px]" />
        <div className="absolute inset-0 bg-[radial-gradient(#0e7490_1px,transparent_1px)] [background-size:32px_32px] opacity-15" />
      </div>

      {/* Navigation Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#02050b]/85 border-b border-cyan-900/40 px-4 lg:px-8 py-3 flex items-center justify-between shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="flex items-center gap-3.5">
          <div className="relative group cursor-pointer" onClick={() => go("landing")}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 p-[1px] shadow-[0_0_20px_rgba(6,182,212,0.4)]">
              <img
                src="/securescope-logo.png"
                alt="SecureScope Logo"
                className="w-full h-full object-cover rounded-[11px]"
              />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-(--font-orbitron) text-base font-extrabold tracking-wider text-white">
                SECURE<span className="text-cyan-400">SCOPE</span>
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-(--font-jetbrains) font-bold bg-cyan-500/15 border border-cyan-400/30 text-cyan-300 uppercase tracking-widest">
                v2.4 Live
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-(--font-jetbrains) hidden sm:block">
              Continuous Human + AI Penetration Orchestration
            </p>
          </div>
        </div>

        {/* Live System Indicators */}
        <div className="hidden lg:flex items-center gap-4 font-(--font-jetbrains) text-xs">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.15)]">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span className="font-bold uppercase tracking-wider text-[11px]">Pen-Test Engine: Active</span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-slate-300">
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span>Workers: <strong className="text-cyan-300">8/8 Online</strong></span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-slate-300">
            <ShieldCheck className="w-3.5 h-3.5 text-violet-400" />
            <span>Scope Boundary: <strong className="text-violet-300">Enforced</strong></span>
          </div>
        </div>

        {/* Login CTA Button */}
        <div className="flex items-center gap-3">
          {authenticated ? (
            <button
              onClick={() => go("dashboard")}
              className="px-4 py-2.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/40 text-emerald-300 font-(--font-jetbrains) text-xs font-bold uppercase tracking-wider flex items-center gap-2 transition-all shadow-[0_0_20px_rgba(16,185,129,0.25)] cursor-pointer"
            >
              <BarChart3 className="w-4 h-4 text-emerald-400" />
              <span>Buka Konsol Operator</span>
            </button>
          ) : (
            <button
              onClick={() => go("login")}
              className="relative group px-5 py-2.5 rounded-lg bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-black font-(--font-jetbrains) text-xs font-extrabold uppercase tracking-wider flex items-center gap-2 transition-all duration-300 shadow-[0_0_25px_rgba(6,182,212,0.45)] hover:shadow-[0_0_35px_rgba(6,182,212,0.65)] cursor-pointer"
            >
              <LogIn className="w-4 h-4 text-black group-hover:scale-110 transition-transform" />
              <span>Masuk Console</span>
              <ChevronRight className="w-3.5 h-3.5 text-black group-hover:translate-x-1 transition-transform" />
            </button>
          )}
        </div>
      </header>

      {/* Main Container */}
      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
        {/* Hero Section Container */}
        <div className="text-center space-y-5 max-w-5xl mx-auto">
          {/* Cyber Status Badge */}
          <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-gradient-to-r from-cyan-950/80 via-blue-950/60 to-purple-950/80 border border-cyan-400/40 text-cyan-300 font-(--font-jetbrains) text-xs font-semibold uppercase tracking-widest shadow-[0_0_20px_rgba(6,182,212,0.2)]">
            <Sparkles className="w-4 h-4 text-cyan-400 animate-spin" />
            <span>OFFENSIVE SECURITY VALIDATION CONTROL PLATFORM</span>
          </div>

          {/* Cyber Attack Simulation Graphic Banner (Live Animated 60FPS Canvas) */}
          <div className="relative rounded-2xl overflow-hidden border border-cyan-500/50 shadow-[0_0_60px_rgba(6,182,212,0.3)] group bg-[#01040a] min-h-[320px] sm:min-h-[380px] flex items-center justify-center">
            {/* Background World Map Graphic Blend */}
            <img
              src="/securescope-world-map.png"
              alt="Live Cyber Threat World Map Attack Simulation"
              className="absolute inset-0 w-full h-full object-cover object-center filter brightness-90 contrast-110 opacity-55 pointer-events-none"
            />

            {/* Live Interactive 60FPS Attack Canvas */}
            <canvas ref={heroAttackCanvasRef} className="relative z-10 w-full h-[360px] block cursor-crosshair" />

            {/* Dark Gradient Overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-[#02050b] via-transparent to-black/50 pointer-events-none z-20" />

            {/* Top Left Live Status HUD */}
            <div className="absolute top-4 left-4 z-30 bg-[#020617]/90 backdrop-blur-md px-4 py-2 rounded-xl border border-cyan-500/40 flex items-center gap-2.5 shadow-lg">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
              <span className="font-(--font-jetbrains) text-xs font-extrabold text-cyan-300 tracking-wider uppercase">
                GLOBAL THREAT MAP :: LIVE ATTACK VECTOR SIMULATION
              </span>
            </div>

            {/* Top Right Live Telemetry HUD */}
            <div className="absolute top-4 right-4 z-30 bg-[#020617]/90 backdrop-blur-md px-3.5 py-2 rounded-xl border border-cyan-900/60 flex items-center gap-2.5 text-xs font-(--font-jetbrains) text-slate-300 shadow-lg">
              <Flame className="w-4 h-4 text-red-500 animate-pulse" />
              <span>PAYLOAD INJECTION: <strong className="text-cyan-400">ACTIVE (1,480 req/s)</strong></span>
            </div>

            {/* Bottom Overlay Live Rotating Attack Phase Strip */}
            <div className="absolute bottom-4 inset-x-4 z-30 bg-[#01040a]/90 backdrop-blur-md p-3.5 rounded-xl border border-cyan-500/40 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-(--font-jetbrains) shadow-2xl">
              <div className="flex items-center gap-2.5 text-slate-200">
                <ShieldAlert className="w-4 h-4 text-cyan-400 flex-shrink-0 animate-pulse" />
                <span>
                  SIMULASI VEKTOR EXPLOIT:{" "}
                  <strong className="text-cyan-300 font-bold">
                    {ATTACK_PHASES[heroAttackPhase].title} ({ATTACK_PHASES[heroAttackPhase].detail})
                  </strong>
                </span>
              </div>
              <div className="flex items-center gap-2 text-emerald-400 font-bold bg-emerald-500/15 px-3 py-1 rounded-lg border border-emerald-500/30">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>SCOPE BOUNDARY ENFORCED</span>
              </div>
            </div>
          </div>

          {/* Preset Target Switches */}
          <div className="pt-2 flex flex-wrap justify-center items-center gap-2">
            <span className="text-xs font-(--font-jetbrains) text-slate-400 uppercase tracking-widest mr-2">Pilih Target Simulasi:</span>
            {PRESET_TARGETS.map((target) => {
              const active = selectedTarget.id === target.id && !customDomain;
              return (
                <button
                  key={target.id}
                  onClick={() => {
                    setSelectedTarget(target);
                    setCustomDomain("");
                    setLogs([]);
                    setIsScanning(true);
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-(--font-jetbrains) transition-all flex items-center gap-1.5 border cursor-pointer ${
                    active
                      ? "bg-cyan-500/20 border-cyan-400 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.3)] font-bold"
                      : "bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                  }`}
                >
                  <Crosshair className={`w-3.5 h-3.5 ${active ? "text-cyan-400" : "text-slate-500"}`} />
                  <span>{target.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Live Command Center Visual Workspace */}
        <div className="bg-[#030816]/95 rounded-2xl border border-cyan-900/50 p-4 sm:p-6 shadow-[0_0_60px_rgba(2,6,23,0.9)] backdrop-blur-2xl space-y-6">
          {/* Controls & Mode Bar */}
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4 pb-4 border-b border-cyan-900/30">
            {/* Custom Domain Input */}
            <form onSubmit={handleStartCustomScan} className="flex-1 flex items-center gap-2">
              <div className="relative flex-1">
                <Globe className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-cyan-500" />
                <input
                  type="text"
                  placeholder="Masukkan domain target (cth: api.perusahaan.co.id)..."
                  value={customDomain}
                  onChange={(e) => setCustomDomain(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-[#010409] border border-cyan-900/50 rounded-xl font-(--font-jetbrains) text-xs text-cyan-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 transition-all"
                />
              </div>
              <button
                type="submit"
                className="px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 font-(--font-jetbrains) text-xs font-bold flex items-center gap-2 transition-all cursor-pointer"
              >
                <Zap className="w-3.5 h-3.5 text-cyan-400" />
                <span>Simulasi Domain</span>
              </button>
            </form>

            {/* Mode Switcher Tabs */}
            <div className="flex items-center gap-2 self-end lg:self-auto">
              <div className="flex bg-[#010409] p-1 rounded-xl border border-cyan-900/40">
                <button
                  onClick={() => setActiveTab("topology")}
                  className={`px-3 py-1.5 rounded-lg font-(--font-jetbrains) text-xs flex items-center gap-1.5 transition-all cursor-pointer ${
                    activeTab === "topology" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold shadow-[0_0_12px_rgba(6,182,212,0.2)]" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Radar className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Radar Topologi</span>
                </button>

                <button
                  onClick={() => setActiveTab("terminal")}
                  className={`px-3 py-1.5 rounded-lg font-(--font-jetbrains) text-xs flex items-center gap-1.5 transition-all cursor-pointer ${
                    activeTab === "terminal" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold shadow-[0_0_12px_rgba(6,182,212,0.2)]" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Terminal className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Live Terminal</span>
                </button>

                <button
                  onClick={() => setActiveTab("vectors")}
                  className={`px-3 py-1.5 rounded-lg font-(--font-jetbrains) text-xs flex items-center gap-1.5 transition-all cursor-pointer ${
                    activeTab === "vectors" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold shadow-[0_0_12px_rgba(6,182,212,0.2)]" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <ShieldAlert className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Vektor Riset</span>
                </button>
              </div>

              {/* Scan Play/Pause & Speed */}
              <div className="flex items-center gap-1 bg-[#010409] p-1 rounded-xl border border-cyan-900/40">
                <button
                  onClick={() => setIsScanning(!isScanning)}
                  className={`p-2 rounded-lg font-(--font-jetbrains) text-xs transition-all cursor-pointer ${
                    isScanning
                      ? "bg-amber-500/20 text-amber-400"
                      : "bg-emerald-500/20 text-emerald-400"
                  }`}
                  title={isScanning ? "Jeda Stream" : "Mulai Stream"}
                >
                  {isScanning ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                </button>

                {([1, 2, 5] as const).map((spd) => (
                  <button
                    key={spd}
                    onClick={() => setScanSpeed(spd)}
                    className={`px-2 py-1 rounded font-(--font-jetbrains) text-[11px] font-bold cursor-pointer ${
                      scanSpeed === spd ? "bg-cyan-500/30 text-cyan-300 border border-cyan-400/50" : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {spd}x
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Main Visual Display Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Box: Radar Canvas or Terminal */}
            <div className="lg:col-span-8 flex flex-col space-y-4">
              {activeTab === "topology" ? (
                <div className="relative bg-[#010409] rounded-xl border border-cyan-900/40 p-2 h-[430px] overflow-hidden flex flex-col justify-between">
                  <canvas ref={canvasRef} className="w-full h-full block cursor-pointer" />

                  {/* Interactive Node Telemetry HUD Bar */}
                  {selectedNode && (
                    <div className="absolute top-4 right-4 bg-[#020713]/90 backdrop-blur-md p-3.5 rounded-xl border border-cyan-500/30 text-xs font-(--font-jetbrains) text-slate-300 space-y-2 max-w-xs shadow-[0_0_20px_rgba(0,0,0,0.8)]">
                      <div className="flex items-center justify-between border-b border-cyan-900/40 pb-2">
                        <span className="font-bold text-cyan-300 flex items-center gap-1.5">
                          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: selectedNode.color }} />
                          {selectedNode.label}
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold">
                          {selectedNode.status}
                        </span>
                      </div>
                      <div className="space-y-1 text-[11px]">
                        <div className="flex justify-between"><span className="text-slate-500">Peran Node:</span> <span className="text-slate-200">{selectedNode.role}</span></div>
                        <div className="flex justify-between"><span className="text-slate-500">Alamat IP:</span> <span className="text-cyan-400">{selectedNode.ip}</span></div>
                        <div className="flex justify-between"><span className="text-slate-500">Ping Latency:</span> <span className="text-emerald-400">{selectedNode.latency}</span></div>
                        <div className="flex justify-between"><span className="text-slate-500">Payload Packets:</span> <span className="text-violet-400">{selectedNode.packets.toLocaleString()} pkts</span></div>
                      </div>
                      <p className="text-[10px] text-slate-400 italic pt-1 border-t border-cyan-900/30">
                        Klik pada node mana saja di canvas radar untuk melihat telemetry.
                      </p>
                    </div>
                  )}

                  <div className="absolute bottom-4 left-4 bg-black/80 backdrop-blur-md px-3 py-2 rounded-lg border border-cyan-900/50 text-[11px] font-(--font-jetbrains) text-slate-300 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-400" /> Target Gateway ({selectedTarget.name})
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-violet-500" /> AI Agent Workers (Parallel Execution)
                    </div>
                  </div>
                </div>
              ) : activeTab === "terminal" ? (
                <div className="bg-[#010409] rounded-xl border border-cyan-900/40 p-4 font-(--font-jetbrains) text-xs flex flex-col h-[430px]">
                  {/* Terminal Header */}
                  <div className="flex items-center justify-between pb-3 mb-3 border-b border-cyan-900/30">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
                      <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
                      <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
                      <span className="text-[11px] text-slate-400 ml-2 font-bold">
                        SECURE-SCOPE-SHELL :: {customDomain || selectedTarget.domain}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-slate-400">
                      <span className="flex items-center gap-1 text-cyan-400 font-bold">
                        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
                        STREAMING
                      </span>
                      <span>Kecepatan: {scanSpeed}x</span>
                    </div>
                  </div>

                  {/* Terminal Log Stream */}
                  <div ref={terminalRef} className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-thin scrollbar-thumb-cyan-900">
                    {logs.length === 0 ? (
                      <div className="h-full flex items-center justify-center text-slate-600 italic">
                        Menyiapkan stream log penetration testing...
                      </div>
                    ) : (
                      logs.map((log) => {
                        let levelBg = "text-slate-400 bg-slate-800/40 border-slate-700";
                        if (log.level === "SCOPE") levelBg = "text-cyan-400 bg-cyan-500/10 border-cyan-500/30";
                        if (log.level === "RECON") levelBg = "text-violet-400 bg-violet-500/10 border-violet-500/30";
                        if (log.level === "EXPLOIT") levelBg = "text-amber-400 bg-amber-500/10 border-amber-500/30";
                        if (log.level === "VULN") levelBg = "text-red-400 bg-red-500/15 border-red-500/40 font-bold animate-pulse";
                        if (log.level === "PROOF") levelBg = "text-pink-400 bg-pink-500/10 border-pink-500/30";
                        if (log.level === "SUCCESS") levelBg = "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";

                        return (
                          <div key={log.id} className="flex items-start gap-2 leading-relaxed">
                            <span className="text-slate-500 select-none font-sans text-[10px] pt-0.5">{log.time}</span>
                            <span className={`px-1.5 py-0.2 rounded border text-[10px] font-bold ${levelBg}`}>
                              {log.level}
                            </span>
                            <span className="text-cyan-600">[{log.module}]</span>
                            <span className="text-slate-200 flex-1">{log.message}</span>
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Terminal Footer Bar */}
                  <div className="pt-3 mt-2 border-t border-cyan-900/30 flex items-center justify-between text-[11px] text-slate-500">
                    <div>
                      Scope Status: <strong className="text-emerald-400">AUTHORIZED (SHA-256 Valid)</strong>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleDownloadEvidence}
                        className="hover:text-cyan-300 transition-colors flex items-center gap-1 cursor-pointer"
                      >
                        <Download className="w-3 h-3 text-cyan-400" /> Evidence JSON
                      </button>
                      <button
                        onClick={() => setLogs([])}
                        className="hover:text-slate-300 transition-colors flex items-center gap-1 cursor-pointer"
                      >
                        <RefreshCw className="w-3 h-3" /> Clear
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-[#010409] rounded-xl border border-cyan-900/40 p-5 h-[430px] overflow-y-auto space-y-4">
                  <h3 className="font-(--font-jetbrains) text-sm font-bold text-cyan-300 flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-cyan-400" />
                    Vektor Pengujian Pen-Test Aktif
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {PEN_TEST_SCENARIOS.map((sec, idx) => (
                      <div
                        key={sec.id}
                        className={`p-4 rounded-xl border transition-all ${
                          idx === activeVectorIndex
                            ? "bg-cyan-500/10 border-cyan-400/60 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
                            : "bg-slate-900/40 border-slate-800"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="px-2 py-0.5 rounded text-[10px] font-(--font-jetbrains) bg-violet-500/10 border border-violet-500/30 text-violet-400">
                            {sec.category}
                          </span>
                          <span className="text-[10px] font-(--font-jetbrains) font-bold text-red-400 uppercase">
                            Risk: {sec.risk}
                          </span>
                        </div>
                        <h4 className="font-(--font-jetbrains) text-xs font-bold text-white mb-1">{sec.name}</h4>
                        <p className="text-[11px] text-slate-400 font-sans leading-relaxed">{sec.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right Panel: Telemetry & Operator Callout */}
            <div className="lg:col-span-4 flex flex-col justify-between space-y-4">
              {/* Target Info Card */}
              <div className="bg-[#010409] p-4 rounded-xl border border-cyan-900/40 space-y-3 font-(--font-jetbrains)">
                <div className="flex items-center justify-between text-xs border-b border-cyan-900/30 pb-2">
                  <span className="text-slate-400">Target Audit Detail</span>
                  <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Scope Verified
                  </span>
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="text-white font-bold text-sm">{selectedTarget.name}</div>
                  <div className="text-cyan-400 text-xs">{selectedTarget.domain}</div>
                  <div className="text-slate-400 text-[11px]">Tipe: {selectedTarget.type}</div>
                  <div className="text-violet-400 text-[11px]">Batas Risiko: {selectedTarget.riskTier}</div>
                </div>
              </div>

              {/* Live Ticking Telemetry Cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#010409] p-3.5 rounded-xl border border-cyan-900/40 space-y-1">
                  <div className="text-[10px] font-(--font-jetbrains) text-slate-400 uppercase">Total Payload Probes</div>
                  <div className="text-xl font-(--font-jetbrains) font-bold text-cyan-400 flex items-center gap-2">
                    {probesCount.toLocaleString()}
                    <Activity className="w-4 h-4 text-cyan-500 animate-pulse" />
                  </div>
                </div>

                <div className="bg-[#010409] p-3.5 rounded-xl border border-cyan-900/40 space-y-1">
                  <div className="text-[10px] font-(--font-jetbrains) text-slate-400 uppercase">Risk Confirmed</div>
                  <div className="text-xl font-(--font-jetbrains) font-bold text-red-400 flex items-center gap-2">
                    {vulnFound}
                    <Flame className="w-4 h-4 text-red-500" />
                  </div>
                </div>
              </div>

              {/* Guarantees Box */}
              <div className="bg-gradient-to-br from-cyan-950/40 via-blue-950/20 to-slate-900/50 p-4 rounded-xl border border-cyan-500/20 space-y-2">
                <div className="flex items-center gap-2 text-xs font-(--font-jetbrains) font-bold text-cyan-300">
                  <ShieldCheck className="w-4 h-4 text-cyan-400" />
                  <span>Enforceable Safety Guarantees</span>
                </div>
                <ul className="text-[11px] text-slate-300 space-y-1.5 font-sans">
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Jaminan zero disruption pada beban produksi.</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Aktivasi kill-switch darurat instan.</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Ledger bukti risiko SHA-256 yang dapat diaudit.</span>
                  </li>
                </ul>
              </div>

              {/* Prominent Login Callout */}
              <div className="bg-gradient-to-r from-cyan-500/20 to-blue-600/20 p-5 rounded-xl border border-cyan-400/40 space-y-3 shadow-[0_0_25px_rgba(6,182,212,0.2)]">
                <div className="space-y-1">
                  <h4 className="font-(--font-jetbrains) text-sm font-bold text-white flex items-center gap-2">
                    <Lock className="w-4 h-4 text-cyan-400" />
                    Akses Konsol Security Operator
                  </h4>
                  <p className="text-xs text-slate-300 font-sans leading-relaxed">
                    Masuk ke portal utama untuk mengelola otorisasi pen-test, memantau worker AI, dan mengunduh laporan bukti risiko resmi.
                  </p>
                </div>

                <button
                  onClick={() => go("login")}
                  className="w-full py-3 rounded-lg bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-black font-(--font-jetbrains) text-xs font-extrabold uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-[0_0_25px_rgba(6,182,212,0.4)] cursor-pointer"
                >
                  <LogIn className="w-4 h-4 text-black" />
                  <span>MASUK KE HALAMAN LOGIN</span>
                  <ArrowRight className="w-4 h-4 text-black" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Feature Grid Section */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6">
          <div className="bg-[#030816]/70 p-6 rounded-2xl border border-cyan-900/30 space-y-3 hover:border-cyan-500/40 transition-all group">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 group-hover:scale-110 transition-transform">
              <Crosshair className="w-5 h-5" />
            </div>
            <h3 className="font-(--font-orbitron) text-sm font-bold text-white">Controlled Scope Enforcer</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-sans">
              Pengujian dibatasi tanda tangan kriptografi CIDR, domain whitelist, dan jendela waktu terverifikasi.
            </p>
          </div>

          <div className="bg-[#030816]/70 p-6 rounded-2xl border border-cyan-900/30 space-y-3 hover:border-cyan-500/40 transition-all group">
            <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/30 flex items-center justify-center text-violet-400 group-hover:scale-110 transition-transform">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-(--font-orbitron) text-sm font-bold text-white">Hybrid Human + AI Intelligence</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-sans">
              Eksplorasi payload presisi tinggi AI Agent dipadu pengawasan validator manusia untuk kepatuhan OJK & ISO 27001.
            </p>
          </div>

          <div className="bg-[#030816]/70 p-6 rounded-2xl border border-cyan-900/30 space-y-3 hover:border-cyan-500/40 transition-all group">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 group-hover:scale-110 transition-transform">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="font-(--font-orbitron) text-sm font-bold text-white">Cryptographic Proof-of-Risk</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-sans">
              Menghasilkan bukti kerentanan non-destruktif dengan timestamp dan tanda tangan SHA-256 resmi.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-cyan-900/30 py-8 px-4 sm:px-8 mt-12 bg-[#010408]">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 font-(--font-jetbrains) text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-cyan-500" />
            <span>SecureScope Platform &copy; 2026. Human + AI Security Validation Control.</span>
          </div>

          <div className="flex items-center gap-4">
            <button onClick={() => go("login")} className="hover:text-cyan-400 transition-colors flex items-center gap-1 cursor-pointer">
              <LogIn className="w-3.5 h-3.5" /> Operator Login
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
