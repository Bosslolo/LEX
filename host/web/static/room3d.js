/**
 * Big LEX room — radio heat + camera/faces + BLE devices.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const C = {
  tx: 0x00d2ff,
  rx: 0xffb020,
  cam: 0xf0b429,
  phone: 0x7aa2ff,
  floor: 0x0c1422,
};

const GRID = 32;
const ROOM_W = 16;
const ROOM_D = 12;

export class RoomScene {
  constructor(container) {
    this.el = container;
    this.layers = { csi: true, cam: true, phone: true };
    this.topDown = true;
    this._data = null;
    this._clock = new THREE.Clock();

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    this.renderer.setClearColor(0x04070e, 1);
    this.renderer.shadowMap.enabled = true;
    this.el.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x04070e, 0.022);

    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 120);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.target.set(0, 0.3, 0);
    this._setCameraTop();

    this.scene.add(new THREE.AmbientLight(0x6a7a8a, 0.45));
    const key = new THREE.DirectionalLight(0xffffff, 0.95);
    key.position.set(6, 14, 4);
    key.castShadow = true;
    this.scene.add(key);
    const fill = new THREE.PointLight(0x2090ff, 0.55, 30);
    fill.position.set(-5, 4, -3);
    this.scene.add(fill);
    const warm = new THREE.PointLight(0xffb020, 0.4, 28);
    warm.position.set(5, 3.5, 3);
    this.scene.add(warm);

    this._buildRoom();
    this._buildAmbientDust();
    this._buildBoards();
    this._buildSignalField();
    this._fieldSmooth = new Float32Array(GRID * GRID);
    this._people = [];
    this._phones = [];

    window.addEventListener("resize", () => this._resize());
    this._resize();
    this._raf = requestAnimationFrame(() => this._tick());
  }

  setLayers({ csi, cam, phone }) {
    if (csi != null) this.layers.csi = csi;
    if (cam != null) this.layers.cam = cam;
    if (phone != null) this.layers.phone = phone;
    this._sigMesh.visible = this.layers.csi;
  }

  setTopDown(on) {
    this.topDown = on;
    if (on) this._setCameraTop();
    else this._setCameraOrbit();
  }

  update(data) {
    this._data = data;
  }

  _setCameraTop() {
    this.camera.position.set(0, 18, 0.02);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  _setCameraOrbit() {
    this.camera.position.set(11, 8, 11);
    this.controls.target.set(0, 0.4, 0);
    this.controls.update();
  }

  _buildRoom() {
    const grid = new THREE.GridHelper(ROOM_W, 32, 0x1a4830, 0x0c2818);
    grid.material.opacity = 0.45;
    grid.material.transparent = true;
    this.scene.add(grid);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(ROOM_W, ROOM_D),
      new THREE.MeshStandardMaterial({
        color: C.floor,
        roughness: 0.78,
        metalness: 0.22,
        emissive: 0x03060c,
        emissiveIntensity: 0.12,
      })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);

    const edges = new THREE.EdgesGeometry(new THREE.BoxGeometry(ROOM_W, 4, ROOM_D));
    const roomWire = new THREE.LineSegments(
      edges,
      new THREE.LineBasicMaterial({ color: 0x245a8a, transparent: true, opacity: 0.35 })
    );
    roomWire.position.y = 2;
    this.scene.add(roomWire);
  }

  _buildAmbientDust() {
    const n = 900;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * ROOM_W;
      pos[i * 3 + 1] = Math.random() * 3.2;
      pos[i * 3 + 2] = (Math.random() - 0.5) * ROOM_D;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this._dust = new THREE.Points(
      geo,
      new THREE.PointsMaterial({
        color: 0x6a9bb8,
        size: 0.035,
        transparent: true,
        opacity: 0.35,
        depthWrite: false,
      })
    );
    this.scene.add(this._dust);
  }

  _makeLabel(text, color) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 96;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, 256, 96);
    ctx.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
    ctx.font = "bold 48px Bahnschrift, Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(text).slice(0, 14), 128, 48);
    const tex = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
    const spr = new THREE.Sprite(mat);
    spr.scale.set(1.8, 0.65, 1);
    spr.position.set(0, 0.85, 0);
    return spr;
  }

  _makeBoard(label, labelColor, x, z) {
    const g = new THREE.Group();
    g.position.set(x, 0.9, z);
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.7, 0.14, 0.4),
      new THREE.MeshStandardMaterial({ color: 0x505060, metalness: 0.7, roughness: 0.22 })
    );
    body.castShadow = true;
    g.add(body);
    for (let i = -1; i <= 1; i++) {
      const ant = new THREE.Mesh(
        new THREE.CylinderGeometry(0.014, 0.014, 0.4),
        new THREE.MeshStandardMaterial({ color: 0x808088, metalness: 0.55 })
      );
      ant.position.set(i * 0.2, 0.28, 0);
      ant.rotation.z = i * 0.12;
      g.add(ant);
    }
    const led = new THREE.Mesh(
      new THREE.SphereGeometry(0.05),
      new THREE.MeshBasicMaterial({ color: labelColor })
    );
    led.position.set(0.24, 0.08, 0.16);
    g.add(led);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.45, 0.75, 48),
      new THREE.MeshBasicMaterial({
        color: labelColor,
        transparent: true,
        opacity: 0.18,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = -0.88;
    g.add(ring);
    const light = new THREE.PointLight(labelColor, 1.2, 8);
    light.position.set(0, 0.3, 0);
    g.add(light);
    const spr = this._makeLabel(label, labelColor);
    spr.position.set(0, 1.0, 0);
    g.add(spr);
    g.userData.led = led;
    g.userData.light = light;
    g.userData.ring = ring;
    this.scene.add(g);
    return g;
  }

  _buildBoards() {
    this.tx = this._makeBoard("TX", C.tx, -ROOM_W / 2 + 0.9, 0);
    this.rx = this._makeBoard("RX", C.rx, ROOM_W / 2 - 0.9, 0);
  }

  _buildSignalField() {
    const cellW = ROOM_W / GRID;
    const cellD = ROOM_D / GRID;
    const geo = new THREE.PlaneGeometry(cellW * 0.9, cellD * 0.9);
    const mat = new THREE.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    this._sigMesh = new THREE.InstancedMesh(geo, mat, GRID * GRID);
    this._sigMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this._sigColors = new Float32Array(GRID * GRID * 3);
    this._sigMesh.instanceColor = new THREE.InstancedBufferAttribute(this._sigColors, 3);
    const dummy = new THREE.Object3D();
    for (let z = 0; z < GRID; z++) {
      for (let x = 0; x < GRID; x++) {
        const i = z * GRID + x;
        dummy.position.set((x - GRID / 2 + 0.5) * cellW, 0.03, (z - GRID / 2 + 0.5) * cellD);
        dummy.rotation.x = -Math.PI / 2;
        dummy.updateMatrix();
        this._sigMesh.setMatrixAt(i, dummy.matrix);
        this._sigColors[i * 3] = 0.02;
        this._sigColors[i * 3 + 1] = 0.06;
        this._sigColors[i * 3 + 2] = 0.1;
      }
    }
    this._sigMesh.instanceMatrix.needsUpdate = true;
    this._sigMesh.instanceColor.needsUpdate = true;
    this.scene.add(this._sigMesh);
    this._dummy = dummy;
    this._cellW = cellW;
    this._cellD = cellD;
  }

  _heatColor(v, out, i) {
    let r, g, b;
    if (v < 0.25) {
      r = 0.03; g = 0.05 + v * 1.8; b = 0.08 + v * 1.8;
    } else if (v < 0.5) {
      r = 0.03; g = 0.2 + (v - 0.25) * 2.4; b = 0.5 - (v - 0.25) * 1.2;
    } else if (v < 0.75) {
      r = (v - 0.5) * 4; g = 0.7 + (v - 0.5) * 0.6; b = 0.1;
    } else {
      r = 1; g = 1 - (v - 0.75) * 3; b = 0.05;
    }
    out[i * 3] = r; out[i * 3 + 1] = g; out[i * 3 + 2] = b;
  }

  _ensurePeople(n) {
    while (this._people.length < n) {
      const g = new THREE.Group();
      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.2),
        new THREE.MeshBasicMaterial({ color: C.cam })
      );
      head.position.y = 1.55;
      const body = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.24, 0.75, 6, 12),
        new THREE.MeshBasicMaterial({ color: C.cam })
      );
      body.position.y = 0.8;
      const glow = new THREE.PointLight(C.cam, 0.9, 3.5);
      glow.position.y = 1.3;
      const label = this._makeLabel("?", C.cam);
      label.position.set(0, 2.2, 0);
      label.scale.set(2.4, 0.75, 1);
      g.add(head, body, glow, label);
      g.userData.label = label;
      g.visible = false;
      this.scene.add(g);
      this._people.push(g);
    }
  }

  _ensurePhones(n) {
    while (this._phones.length < n) {
      const g = new THREE.Group();
      const phone = new THREE.Mesh(
        new THREE.BoxGeometry(0.28, 0.55, 0.06),
        new THREE.MeshStandardMaterial({
          color: 0x1a2233,
          metalness: 0.55,
          roughness: 0.35,
          emissive: C.phone,
          emissiveIntensity: 0.25,
        })
      );
      phone.position.y = 0.9;
      phone.castShadow = true;
      const beam = new THREE.Mesh(
        new THREE.CylinderGeometry(0.02, 0.18, 0.9, 16, 1, true),
        new THREE.MeshBasicMaterial({
          color: C.phone,
          transparent: true,
          opacity: 0.22,
          depthWrite: false,
        })
      );
      beam.position.y = 0.45;
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.25, 0.4, 32),
        new THREE.MeshBasicMaterial({
          color: C.phone,
          transparent: true,
          opacity: 0.35,
          side: THREE.DoubleSide,
          depthWrite: false,
        })
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.04;
      const label = this._makeLabel("DEV", C.phone);
      label.position.set(0, 1.55, 0);
      label.scale.set(2.0, 0.65, 1);
      const light = new THREE.PointLight(C.phone, 0.7, 3);
      light.position.y = 1.1;
      g.add(phone, beam, ring, label, light);
      g.userData.label = label;
      g.userData.beam = beam;
      g.visible = false;
      this.scene.add(g);
      this._phones.push(g);
    }
  }

  _setLabel(spr, text, color) {
    if (!spr) return;
    const key = `${text}|${color}`;
    if (spr.userData.labelKey === key) return;
    spr.userData.labelKey = key;
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 96;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, 256, 96);
    ctx.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
    ctx.font = "bold 40px Bahnschrift, Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(text || "?").slice(0, 14), 128, 48);
    if (spr.material.map) spr.material.map.dispose();
    spr.material.map = new THREE.CanvasTexture(canvas);
    spr.material.needsUpdate = true;
  }

  _applyField(values) {
    if (!values || !values.length) return;
    const dummy = this._dummy;
    const srcG = Math.round(Math.sqrt(values.length));
    for (let z = 0; z < GRID; z++) {
      for (let x = 0; x < GRID; x++) {
        const i = z * GRID + x;
        // resample if host still sends 20x20
        let raw;
        if (srcG === GRID) raw = values[i] || 0;
        else {
          const sx = Math.min(srcG - 1, Math.floor((x / GRID) * srcG));
          const sz = Math.min(srcG - 1, Math.floor((z / GRID) * srcG));
          raw = values[sz * srcG + sx] || 0;
        }
        this._fieldSmooth[i] = this._fieldSmooth[i] * 0.84 + raw * 0.16;
        const v = this._fieldSmooth[i];
        const s = v > 0.06 ? 0.65 + v * 0.7 : 0.18;
        dummy.position.set(
          (x - GRID / 2 + 0.5) * this._cellW,
          0.03,
          (z - GRID / 2 + 0.5) * this._cellD
        );
        dummy.rotation.x = -Math.PI / 2;
        dummy.scale.set(s, s, 1);
        dummy.updateMatrix();
        this._sigMesh.setMatrixAt(i, dummy.matrix);
        this._heatColor(v, this._sigColors, i);
      }
    }
    this._sigMesh.instanceMatrix.needsUpdate = true;
    this._sigMesh.instanceColor.needsUpdate = true;
  }

  _applyPeople(persons) {
    const list = (persons || []).filter((p) => {
      if (!this.layers.cam && (p.source === "camera" || p.source === "face")) return false;
      if (!this.layers.csi && p.source === "csi") return false;
      if (p.source === "phone") return false;
      return true;
    });
    this._ensurePeople(list.length);
    for (let i = 0; i < this._people.length; i++) {
      const g = this._people[i];
      if (i >= list.length) {
        g.visible = false;
        continue;
      }
      const p = list[i];
      const pos = p.position || [0, 0, 0];
      g.visible = true;
      g.position.set(pos[0], 0, pos[2]);
      const side = this._data?.near_side;
      let col = C.cam;
      let label = p.name || (p.source === "csi" ? "RADIO" : `P${i + 1}`);
      if (p.source === "face" || p.name) col = C.tx;
      else if (p.source === "csi") col = side === "rx" ? C.rx : side === "tx" ? C.tx : 0xb0c4de;
      g.children.forEach((c) => {
        if (c.isSprite) return;
        if (c.material && c.material.color) c.material.color.setHex(col);
        if (c.isLight) c.color.setHex(col);
      });
      this._setLabel(g.userData.label, label, col);
    }
  }

  _applyPhones(devices) {
    if (!this.layers.phone) {
      for (const g of this._phones) g.visible = false;
      return;
    }
    const list = devices || [];
    this._ensurePhones(list.length);
    for (let i = 0; i < this._phones.length; i++) {
      const g = this._phones[i];
      if (i >= list.length) {
        g.visible = false;
        continue;
      }
      const d = list[i];
      const pos = d.position || [0, 0, 0];
      g.visible = true;
      g.position.set(pos[0], 0, pos[2]);
      const label = (d.name || "phone").slice(0, 12);
      this._setLabel(g.userData.label, label, C.phone);
      if (g.userData.beam) {
        g.userData.beam.material.opacity = 0.15 + Math.min(0.35, ((d.rssi || -70) + 100) / 120);
      }
    }
  }

  _resize() {
    const w = this.el.clientWidth || 800;
    const h = this.el.clientHeight || 500;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  }

  _tick() {
    const t = this._clock.getElapsedTime();
    const d = this._data;
    if (this._dust) {
      this._dust.rotation.y = t * 0.02;
      this._dust.position.y = Math.sin(t * 0.3) * 0.05;
    }
    if (d) {
      if (this.layers.csi) this._applyField(d.signal_field?.values);
      this._applyPeople(d.room_persons || []);
      this._applyPhones(d.phone_markers || []);
      const side = d.near_side || "none";
      const motion = d.csi_motion || 0;
      const cal = !!d.csi_calibrating;
      const blink = cal && Math.floor(performance.now() / 250) % 2 === 0;
      const boostTx = side === "tx" || side === "mid" ? 1.5 + motion : 1;
      const boostRx = side === "rx" || side === "mid" ? 1.5 + motion : 1;
      this.tx.scale.setScalar(cal ? (blink ? 1.12 : 0.95) : 0.95 + 0.1 * boostTx);
      this.rx.scale.setScalar(cal ? (blink ? 1.12 : 0.95) : 0.95 + 0.1 * boostRx);
      this.tx.userData.light.intensity = (side === "tx" || side === "mid" ? 1.5 : 0.5) + motion;
      this.rx.userData.light.intensity = (side === "rx" || side === "mid" ? 1.5 : 0.5) + motion;
      this.tx.userData.ring.material.opacity = side === "tx" ? 0.55 + motion * 0.35 : 0.14;
      this.rx.userData.ring.material.opacity = side === "rx" ? 0.55 + motion * 0.35 : 0.14;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this._raf = requestAnimationFrame(() => this._tick());
  }
}
