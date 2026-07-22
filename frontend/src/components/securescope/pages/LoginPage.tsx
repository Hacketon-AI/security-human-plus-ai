"use client";

import * as React from "react";
import * as THREE from "three";
import { loginUser, saveToken, saveUser } from "@/lib/securescope/authApi";
import { useApp } from "@/lib/securescope/store";

export function LoginPage() {
  const login = useApp((state) => state.login);
  const go = useApp((state) => state.go);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const cardRef = React.useRef<HTMLDivElement>(null);
  const rightPanelRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let animationId = 0;
    let disposed = false;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      75,
      window.innerWidth / window.innerHeight,
      1,
      1000
    );
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    camera.position.z = 30;

    const particleCount = 1500;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const color1 = new THREE.Color(0x00f2ff);
    const color2 = new THREE.Color(0x7d2ae8);
    for (let index = 0; index < particleCount; index += 1) {
      positions[index * 3] = (Math.random() - 0.5) * 100;
      positions[index * 3 + 1] = (Math.random() - 0.5) * 100;
      positions[index * 3 + 2] = (Math.random() - 0.5) * 100;
      const mixedColor = color1.clone().lerp(color2, Math.random());
      colors[index * 3] = mixedColor.r;
      colors[index * 3 + 1] = mixedColor.g;
      colors[index * 3 + 2] = mixedColor.b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const material = new THREE.PointsMaterial({
      size: 0.15,
      vertexColors: true,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    const coreGeometry = new THREE.IcosahedronGeometry(6, 1);
    const coreMaterial = new THREE.MeshBasicMaterial({
      color: 0x00f2ff,
      wireframe: true,
      transparent: true,
      opacity: 0.15,
    });
    const core = new THREE.Mesh(coreGeometry, coreMaterial);
    scene.add(core);

    let mouseX = 0;
    let mouseY = 0;
    const onMouseMove = (event: MouseEvent) => {
      mouseX = (event.clientX / window.innerWidth) * 2 - 1;
      mouseY = -(event.clientY / window.innerHeight) * 2 + 1;
    };
    const onResize = () => {
      renderer.setSize(window.innerWidth, window.innerHeight);
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
    };
    const animate = () => {
      if (disposed) return;
      animationId = requestAnimationFrame(animate);
      particles.rotation.x += 0.0005;
      particles.rotation.y += 0.001;
      core.rotation.x += 0.003;
      core.rotation.y += 0.005;
      core.scale.setScalar(1 + Math.sin(Date.now() * 0.001) * 0.1);
      camera.position.x += (mouseX * 5 - camera.position.x) * 0.05;
      camera.position.y += (mouseY * 5 - camera.position.y) * 0.05;
      camera.lookAt(scene.position);
      renderer.render(scene, camera);
    };

    document.addEventListener("mousemove", onMouseMove);
    window.addEventListener("resize", onResize);
    animate();
    return () => {
      disposed = true;
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("mousemove", onMouseMove);
      renderer.dispose();
      geometry.dispose();
      material.dispose();
      coreGeometry.dispose();
      coreMaterial.dispose();
    };
  }, []);

  React.useEffect(() => {
    const panel = rightPanelRef.current;
    const card = cardRef.current;
    if (!panel || !card) return;
    const onMove = (event: MouseEvent) => {
      const rect = panel.getBoundingClientRect();
      const rotateX = ((event.clientY - rect.top - rect.height / 2) / (rect.height / 2)) * -10;
      const rotateY = ((event.clientX - rect.left - rect.width / 2) / (rect.width / 2)) * 10;
      card.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    };
    const onLeave = () => {
      card.style.transform = "rotateX(0deg) rotateY(0deg)";
    };
    panel.addEventListener("mousemove", onMove);
    panel.addEventListener("mouseleave", onLeave);
    return () => {
      panel.removeEventListener("mousemove", onMove);
      panel.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await loginUser({ email: email.trim(), password });
      if (!response.user.organization_id) {
        setError("This account is not assigned to an organization. Contact an administrator.");
        return;
      }
      saveToken(response.access_token);
      saveUser(response.user);
      login(response.user.organization_id);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <canvas ref={canvasRef} className="fixed inset-0 z-0 h-screen w-screen pointer-events-none" />
      <div className="ss-login-container">
        <div className="ss-login-left">
          <h1 className="ss-login-logo">SecureScope</h1>
          <p className="ss-login-tagline">
            Orchestrate authorized security validation across your entire infrastructure.
          </p>
          <div className="ss-login-features">
            <div className="ss-login-feature-item">
              <div className="ss-login-feature-icon"><i className="fas fa-shield-halved" /></div>
              <div>
                <h4>Zero Trust Validation</h4>
                <p>Continuously verify access requests.</p>
              </div>
            </div>
            <div className="ss-login-feature-item">
              <div className="ss-login-feature-icon"><i className="fas fa-satellite-dish" /></div>
              <div>
                <h4>Real-time Threat Emulation</h4>
                <p>Simulate authorized security scenarios safely.</p>
              </div>
            </div>
          </div>
        </div>
        <div className="ss-login-right" ref={rightPanelRef}>
          <div className="ss-login-card-container" ref={cardRef}>
            <div className="ss-login-card">
              <div className="ss-login-header">
                <button
                  type="button"
                  onClick={() => go("landing")}
                  className="mb-3 inline-flex items-center gap-1.5 text-xs font-mono text-cyan-400 hover:text-cyan-300 transition-colors cursor-pointer"
                >
                  <i className="fas fa-arrow-left text-[11px]" />
                  <span>Lihat Live System Overview</span>
                </button>
                <h2>Operator Authentication</h2>
                <p>Secure Access Gateway</p>
              </div>
              <form onSubmit={submit}>
                <div className="ss-login-input-group">
                  <label htmlFor="operator-email">Operator Email</label>
                  <div className="ss-login-input-wrapper">
                    <i className="fas fa-envelope" />
                    <input id="operator-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
                  </div>
                </div>
                <div className="ss-login-input-group">
                  <label htmlFor="operator-password">Password</label>
                  <div className="ss-login-input-wrapper">
                    <i className="fas fa-key" />
                    <input id="operator-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
                  </div>
                </div>
                {error && <div className="ss-login-error"><i className="fas fa-circle-exclamation" /><span>{error}</span></div>}
                <button type="submit" className="ss-login-btn-authenticate" disabled={submitting}>
                  <i className={`fas ${submitting ? "fa-spinner fa-spin" : "fa-lock-open"}`} style={{ marginRight: 10 }} />
                  {submitting ? "Authenticating..." : "Authenticate"}
                </button>
                <div className="ss-login-footer-warning"><i className="fas fa-triangle-exclamation" />Authorized personnel only. All actions are monitored.</div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
