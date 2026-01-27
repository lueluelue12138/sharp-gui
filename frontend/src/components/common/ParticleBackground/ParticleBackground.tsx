import React, { useEffect, useRef } from 'react';
import styles from './ParticleBackground.module.css';

interface Particle {
    x: number;
    y: number;
    homeX: number;
    homeY: number;
    vx: number;
    vy: number;
    radius: number;
    color: string;
    floatOffset: number;
    floatSpeedX: number;
    floatSpeedY: number;
}

const CONFIG = {
    baseCount: 250,
    minCount: 150,
    maxCount: 300,
    baseRadius: 2,
    maxRadius: 4,
    floatSpeed: 0.5,
    floatAmplitude: 25,
    mouseRadius: 100,
    mouseForce: 0.06,
    resetSpeed: 0.001,
    colors: [
        "rgba(0, 113, 227, 0.45)",
        "rgba(100, 160, 230, 0.35)",
        "rgba(150, 180, 240, 0.3)",
        "rgba(80, 130, 200, 0.4)",
    ],
};

export const ParticleBackground: React.FC = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const particlesRef = useRef<Particle[]>([]);
    const mouseRef = useRef({ x: -1000, y: -1000 });
    const timeRef = useRef(0);
    const animationRef = useRef<number | null>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Resize
        const resize = () => {
            canvas.width = canvas.offsetWidth;
            canvas.height = canvas.offsetHeight;
        };

        // Particle count based on screen size
        const getParticleCount = (): number => {
            const area = canvas.width * canvas.height;
            const baseArea = 1920 * 1080;
            const count = Math.floor(CONFIG.baseCount * (area / baseArea));
            return Math.max(CONFIG.minCount, Math.min(CONFIG.maxCount, count));
        };

        // Create a particle
        const createParticle = (): Particle => {
            const x = Math.random() * canvas.width;
            const y = Math.random() * canvas.height;
            return {
                x,
                y,
                homeX: x,
                homeY: y,
                vx: 0,
                vy: 0,
                radius: CONFIG.baseRadius + Math.random() * 2,
                color: CONFIG.colors[Math.floor(Math.random() * CONFIG.colors.length)],
                floatOffset: Math.random() * Math.PI * 2,
                floatSpeedX: 0.3 + Math.random() * 0.4,
                floatSpeedY: 0.2 + Math.random() * 0.3,
            };
        };

        // Initialize particles
        const initParticles = () => {
            particlesRef.current = [];
            const count = getParticleCount();
            for (let i = 0; i < count; i++) {
                particlesRef.current.push(createParticle());
            }
        };

        // Animate
        const animate = () => {
            timeRef.current += 0.01;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const particles = particlesRef.current;
            const mouse = mouseRef.current;
            const time = timeRef.current;

            particles.forEach(p => {
                // Natural float
                const floatX = Math.sin(time * p.floatSpeedX + p.floatOffset) * CONFIG.floatAmplitude * 0.3;
                const floatY = Math.cos(time * p.floatSpeedY + p.floatOffset) * CONFIG.floatAmplitude * 0.2;

                const targetX = p.homeX + floatX;
                const targetY = p.homeY + floatY;

                // Mouse interaction
                const dx = mouse.x - p.x;
                const dy = mouse.y - p.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < CONFIG.mouseRadius && dist > 0) {
                    const force = (CONFIG.mouseRadius - dist) / CONFIG.mouseRadius;
                    p.vx -= (dx / dist) * force * CONFIG.mouseForce;
                    p.vy -= (dy / dist) * force * CONFIG.mouseForce;
                } else {
                    p.vx += (targetX - p.x) * CONFIG.resetSpeed;
                    p.vy += (targetY - p.y) * CONFIG.resetSpeed;
                }

                p.x += p.vx;
                p.y += p.vy;
                p.vx *= 0.92;
                p.vy *= 0.92;

                // Boundary wrap
                if (p.x < -50) p.x = canvas.width + 50;
                if (p.x > canvas.width + 50) p.x = -50;
                if (p.y < -50) p.y = canvas.height + 50;
                if (p.y > canvas.height + 50) p.y = -50;

                // Draw
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
                ctx.fillStyle = p.color;
                ctx.fill();
            });

            animationRef.current = requestAnimationFrame(animate);
        };

        // Mouse handlers
        const handleMouseMove = (e: MouseEvent) => {
            const rect = canvas.getBoundingClientRect();
            mouseRef.current.x = e.clientX - rect.left;
            mouseRef.current.y = e.clientY - rect.top;
        };

        const handleMouseLeave = () => {
            mouseRef.current.x = -1000;
            mouseRef.current.y = -1000;
        };

        // Initialize
        resize();
        initParticles();
        animate();

        // Event listeners
        const handleResize = () => {
            resize();
            initParticles();
        };
        window.addEventListener('resize', handleResize);
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseleave', handleMouseLeave);

        return () => {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
            window.removeEventListener('resize', handleResize);
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseleave', handleMouseLeave);
        };
    }, []);

    return (
        <canvas 
            ref={canvasRef} 
            className={styles.canvas} 
            id="particle-canvas"
        />
    );
};
