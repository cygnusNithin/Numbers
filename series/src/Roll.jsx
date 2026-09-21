import React, { useState, useRef, useMemo, useEffect } from 'react';
import * as THREE from 'three';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';

// ============================================================================
// ROLLER CONFIG
// ============================================================================
const ROLLER_SEQUENCE = [7, 6, 8, 5, 9, 0, 3, 1, 2, 4];
const NUM_DIGITS = 10;
const RAD_PER_DIGIT = (Math.PI * 2) / NUM_DIGITS;

// ============================================================================
// TEXTURE - Same as previous working code
// ============================================================================
const createOdometerTexture = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 2048;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');

  // Cream background
  ctx.fillStyle = '#F4F4EC';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const segmentWidth = canvas.width / NUM_DIGITS;

  ctx.fillStyle = '#0A0A0A';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = '900 130px "Arial Black", "Impact", sans-serif';

  ROLLER_SEQUENCE.forEach((digit, index) => {
    const xCenter = index * segmentWidth + segmentWidth / 2;
    const yCenter = canvas.height / 2;

    ctx.save();
    ctx.translate(xCenter, yCenter);
    // CRITICAL: +90deg rotation makes digits upright on horizontal cylinder
    ctx.rotate(Math.PI / 2);
    ctx.fillText(digit.toString(), 0, 0);
    ctx.restore();

    // Divider grooves
    ctx.strokeStyle = '#D4D4C8';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(index * segmentWidth, 0);
    ctx.lineTo(index * segmentWidth, canvas.height);
    ctx.stroke();
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.anisotropy = 16;
  return texture;
};

// ============================================================================
// ROLLER MESH - TRUE PHYSICS (No target, random result)
// ============================================================================
const RollerMesh = ({ spinTrigger, friction, onTelemetry }) => {
  const texture = useMemo(() => createOdometerTexture(), []);
  const meshRef = useRef(null);

  // Physics state
  const angleRef = useRef(0);
  const velocityRef = useRef(0);
  const isSpinningRef = useRef(false);
  const hasSpunRef = useRef(false);

  // Handle spin trigger
  useEffect(() => {
    if (spinTrigger === 0) {
      hasSpunRef.current = false;
      angleRef.current = 0;
      velocityRef.current = 0;
      isSpinningRef.current = false;
      if (meshRef.current) meshRef.current.rotation.y = 0;
      return;
    }

    if (hasSpunRef.current) return;
    hasSpunRef.current = true;

    // TRUE PHYSICS:
    // Random initial velocity (like mechanical lever hitting the roller)
    // Nobody knows where it will stop - physics decides!
    const randomVelocity = -(20 + Math.random() * 30);
    velocityRef.current = randomVelocity;
    isSpinningRef.current = true;

    console.log('🎡 SPIN STARTED');
    console.log('   Initial Velocity:', randomVelocity.toFixed(4), 'rad/f');
    console.log('   Friction:', friction);
    console.log('   Estimated Revolutions:', Math.abs(randomVelocity / (1 - friction) / (Math.PI * 2)).toFixed(1));
  }, [spinTrigger, friction]);

  // Physics loop
  useFrame(() => {
    if (!isSpinningRef.current || !meshRef.current) return;

    // Apply friction decay: ω(t+1) = ω(t) × μ
    velocityRef.current *= friction;
    angleRef.current += velocityRef.current;

    // Rotate around Y axis (horizontal cylinder = vertical wheel)
    meshRef.current.rotation.y = angleRef.current;

    // Calculate current visible digit
    const normalized = ((angleRef.current % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
    const alignOffset = Math.PI / NUM_DIGITS;
    const faceIdx = Math.floor(
      ((Math.PI * 2 - normalized + alignOffset) / RAD_PER_DIGIT) % NUM_DIGITS
    );
    const visibleDigit = ROLLER_SEQUENCE[faceIdx] ?? '-';

    // Send telemetry
    if (onTelemetry) {
      onTelemetry({
        velocity: velocityRef.current.toFixed(5),
        angle: (angleRef.current * (180 / Math.PI)).toFixed(1),
        face: faceIdx,
        digit: visibleDigit,
        isSpinning: true
      });
    }

    // Stop condition
    if (Math.abs(velocityRef.current) < 0.0005) {
      velocityRef.current = 0;
      isSpinningRef.current = false;

      // Final face calculation
      const finalNorm = ((angleRef.current % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
      const alignOffset = Math.PI / NUM_DIGITS;
      const finalFace = Math.floor(
        ((Math.PI * 2 - finalNorm + alignOffset) / RAD_PER_DIGIT) % NUM_DIGITS
      );
      const finalDigit = ROLLER_SEQUENCE[finalFace] ?? '-';

      console.log('✅ STOPPED');
      console.log('   Final Face:', finalFace);
      console.log('   Final Digit:', finalDigit);
      console.log('   Final Angle:', angleRef.current.toFixed(4));

      if (onTelemetry) {
        onTelemetry({
          velocity: '0.00000',
          angle: (angleRef.current * (180 / Math.PI)).toFixed(1),
          face: finalFace,
          digit: finalDigit,
          isSpinning: false
        });
      }
    }
  });

  return (
    // Group tilts cylinder 90° - child mesh rotates on Y axis
    <group rotation={[0, 0, Math.PI / 2]}>
      <mesh ref={meshRef}>
        <cylinderGeometry args={[3, 3, 2.2, 64, 1, true]} />
        <meshStandardMaterial
          map={texture}
          roughness={0.35}
          metalness={0.1}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
};

// ============================================================================
// MAIN APP - CLEAN UI
// ============================================================================
export default function App() {
  const [spinTrigger, setSpinTrigger] = useState(0);
  const [friction, setFriction] = useState(0.985);
  const [phase, setPhase] = useState('idle');
  const [telemetry, setTelemetry] = useState({
    velocity: '0.00000',
    angle: '0.0',
    face: 0,
    digit: '-',
    isSpinning: false
  });

  const handleTelemetry = (data) => {
    setTelemetry(data);
    if (!data.isSpinning && phase === 'spinning') {
      setPhase('done');
    }
  };

  const handleSpin = () => {
    if (phase === 'spinning') return;
    setPhase('spinning');
    setSpinTrigger(t => t + 1);
  };

  const handleReset = () => {
    setSpinTrigger(0);
    setPhase('idle');
    setTelemetry({
      velocity: '0.00000',
      angle: '0.0',
      face: 0,
      digit: '-',
      isSpinning: false
    });
  };

  return (
    <div style={{
      width: '100vw',
      height: '100vh',
      backgroundColor: '#0D0D0D',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'sans-serif',
      overflow: 'hidden',
      color: '#FFF'
    }}>
      {/* Header */}
      <div style={{
        backgroundColor: '#1A1A1A',
        padding: '14px 24px',
        borderBottom: '1px solid #333',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <h1 style={{
            margin: 0,
            color: '#FBBF24',
            fontSize: 20,
            fontFamily: '"Arial Black", sans-serif',
            letterSpacing: 2
          }}>
            🎰 KERALA LOTTERY — ROLLER PHYSICS
          </h1>
          <p style={{ margin: '4px 0 0', color: '#888', fontSize: 11 }}>
            True Physics • Random Result • Sequence: [{ROLLER_SEQUENCE.join(', ')}]
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {/* Friction control */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label style={{ color: '#888', fontSize: 11 }}>
              FRICTION: <span style={{ color: '#fff' }}>{friction}</span>
            </label>
            <input
              type="range"
              min="0.965"
              max="0.992"
              step="0.001"
              value={friction}
              onChange={e => setFriction(parseFloat(e.target.value))}
              style={{ accentColor: '#FBBF24', cursor: 'pointer', width: 100 }}
            />
          </div>

          <button
            onClick={handleSpin}
            disabled={phase === 'spinning'}
            style={{
              background: phase === 'spinning'
                ? '#555'
                : 'linear-gradient(180deg, #FBBF24 0%, #D97706 100%)',
              border: 'none',
              padding: '10px 24px',
              borderRadius: 4,
              color: phase === 'spinning' ? '#888' : '#111',
              fontFamily: '"Arial Black", sans-serif',
              fontSize: 14,
              cursor: phase === 'spinning' ? 'not-allowed' : 'pointer',
              boxShadow: phase === 'spinning' ? 'none' : '0 4px 12px rgba(251,191,36,0.3)'
            }}
          >
            {phase === 'spinning' ? '⟳ SPINNING...' : '⚡ SPIN'}
          </button>

          <button
            onClick={handleReset}
            disabled={phase === 'spinning'}
            style={{
              background: 'transparent',
              border: '1px solid #444',
              padding: '10px 18px',
              borderRadius: 4,
              color: '#888',
              cursor: phase === 'spinning' ? 'not-allowed' : 'pointer',
              fontSize: 13
            }}
          >
            ↺ RESET
          </button>
        </div>
      </div>

      {/* 3D Viewport - FULL HEIGHT */}
      <div style={{ flex: 1, position: 'relative', backgroundColor: '#7A1513' }}>
        <Canvas camera={{ position: [0, 0, 12], fov: 40 }}>
          {/* Lighting */}
          <ambientLight intensity={1.2} />
          <directionalLight position={[10, 20, 15]} intensity={2} castShadow />
          <pointLight position={[-10, -10, 10]} intensity={1} />
          <pointLight position={[0, 0, 8]} intensity={1.5} />

          {/* Bezel frame */}
          <mesh position={[0, 0, -0.2]}>
            <boxGeometry args={[3.6, 5.2, 0.4]} />
            <meshStandardMaterial color="#222" roughness={0.8} />
          </mesh>

          {/* THE ROLLER */}
          <RollerMesh
            spinTrigger={spinTrigger}
            friction={friction}
            onTelemetry={handleTelemetry}
          />

          {/* Red Indicator Line */}
          <mesh position={[0, 0, 3.1]}>
            <boxGeometry args={[2.6, 0.04, 0.1]} />
            <meshBasicMaterial color="#EF4444" />
          </mesh>

          <OrbitControls enableZoom={true} maxDistance={25} minDistance={5} />
        </Canvas>

        {/* Telemetry Overlay */}
        <div style={{
          position: 'absolute',
          top: 16,
          left: 16,
          backgroundColor: 'rgba(0,0,0,0.85)',
          padding: '14px 18px',
          borderRadius: 6,
          border: '1px solid #333',
          fontFamily: 'monospace',
          fontSize: 12,
          color: '#38BDF8',
          pointerEvents: 'none',
          minWidth: 220
        }}>
          <div style={{ color: '#FBBF24', fontWeight: 'bold', marginBottom: 8 }}>
            ⚙ PHYSICS TELEMETRY
          </div>
          <div>VELOCITY (ω): {telemetry.velocity}</div>
          <div>ANGLE (θ): {telemetry.angle}°</div>
          <div>FRICTION (μ): {friction}</div>
          <div style={{
            marginTop: 8,
            paddingTop: 8,
            borderTop: '1px solid #333',
            color: '#fff',
            fontSize: 14
          }}>
            DIGIT: <strong style={{ color: '#FBBF24', fontSize: 20 }}>
              [{telemetry.digit}]
            </strong>
          </div>
          <div style={{
            marginTop: 6,
            fontSize: 11,
            color: phase === 'spinning' ? '#FBBF24'
              : phase === 'done' ? '#00ff88'
              : '#888'
          }}>
            {phase === 'idle' && '◼ READY'}
            {phase === 'spinning' && '⟳ SPINNING'}
            {phase === 'done' && '✓ STOPPED — PHYSICS RESULT'}
          </div>
        </div>

        {/* Result popup */}
        {phase === 'done' && (
          <div style={{
            position: 'absolute',
            top: 16,
            right: 16,
            backgroundColor: 'rgba(0,0,0,0.92)',
            padding: '20px 36px',
            borderRadius: 8,
            border: '2px solid #FBBF24',
            textAlign: 'center',
            pointerEvents: 'none'
          }}>
            <div style={{ color: '#888', fontSize: 10, letterSpacing: 2, marginBottom: 6 }}>
              PHYSICS RESULT
            </div>
            <div style={{
              color: '#FBBF24',
              fontSize: 64,
              fontFamily: '"Arial Black", sans-serif',
              lineHeight: 1
            }}>
              {telemetry.digit}
            </div>
            <div style={{ color: '#555', fontSize: 9, marginTop: 6 }}>
              Determined by physics
            </div>
          </div>
        )}
      </div>
    </div>
  );
}