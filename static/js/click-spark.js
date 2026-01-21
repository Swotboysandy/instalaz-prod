class ClickSpark extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.root = document.documentElement;
    this.svg;
  }

  get active() {
    return this.hasAttribute("active");
  }

  get sparkColor() {
    return this.getAttribute("spark-color") || "#fff";
  }

  get sparkSize() {
    return parseInt(this.getAttribute("spark-size")) || 10;
  }

  get sparkRadius() {
    return parseInt(this.getAttribute("spark-radius")) || 15;
  }

  get sparkCount() {
    return parseInt(this.getAttribute("spark-count")) || 8;
  }

  get duration() {
    return parseInt(this.getAttribute("duration")) || 400;
  }

  get easing() {
    return this.getAttribute("easing") || "ease-out";
  }

  get extraScale() {
    return parseFloat(this.getAttribute("extra-scale")) || 1.0;
  }

  connectedCallback() {
    this.setupCanvas();
    this.setupEvents();
  }

  disconnectedCallback() {
    this.teardownEvents();
  }

  setupCanvas() {
    this.canvas = document.createElement("canvas");
    this.canvas.style.cssText = `
      width: 100%;
      height: 100%;
      display: block;
      user-select: none;
      position: fixed;
      top: 0;
      left: 0;
      pointer-events: none;
      z-index: 9999;
    `;
    this.shadowRoot.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");
    this.sparks = [];
    this.startTime = null;
    
    this.resizeCanvas();
    window.addEventListener("resize", () => this.handleResize());
    
    requestAnimationFrame((t) => this.draw(t));
  }

  setupEvents() {
    this.clickHandler = (e) => this.handleClick(e);
    document.addEventListener("click", this.clickHandler);
  }

  teardownEvents() {
    document.removeEventListener("click", this.clickHandler);
    window.removeEventListener("resize", this.handleResize);
  }

  handleResize() {
    clearTimeout(this.resizeTimeout);
    this.resizeTimeout = setTimeout(() => this.resizeCanvas(), 100);
  }

  resizeCanvas() {
    const { innerWidth, innerHeight } = window;
    if (this.canvas.width !== innerWidth || this.canvas.height !== innerHeight) {
      this.canvas.width = innerWidth;
      this.canvas.height = innerHeight;
    }
  }

  easeFunc(t) {
    switch (this.easing) {
      case "linear":
        return t;
      case "ease-in":
        return t * t;
      case "ease-in-out":
        return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      default: // ease-out
        return t * (2 - t);
    }
  }

  draw(timestamp) {
    if (!this.startTime) {
      this.startTime = timestamp;
    }
    
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    this.sparks = this.sparks.filter((spark) => {
      const elapsed = timestamp - spark.startTime;
      if (elapsed >= this.duration) {
        return false;
      }

      const progress = elapsed / this.duration;
      const eased = this.easeFunc(progress);

      const distance = eased * this.sparkRadius * this.extraScale;
      const lineLength = this.sparkSize * (1 - eased);

      const x1 = spark.x + distance * Math.cos(spark.angle);
      const y1 = spark.y + distance * Math.sin(spark.angle);
      const x2 = spark.x + (distance + lineLength) * Math.cos(spark.angle);
      const y2 = spark.y + (distance + lineLength) * Math.sin(spark.angle);

      this.ctx.strokeStyle = this.sparkColor;
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.moveTo(x1, y1);
      this.ctx.lineTo(x2, y2);
      this.ctx.stroke();

      return true;
    });

    requestAnimationFrame((t) => this.draw(t));
  }

  handleClick(e) {
    const x = e.clientX;
    const y = e.clientY;
    const now = performance.now();
    
    const newSparks = Array.from({ length: this.sparkCount }, (_, i) => ({
      x,
      y,
      angle: (2 * Math.PI * i) / this.sparkCount,
      startTime: now,
    }));

    this.sparks.push(...newSparks);
  }
}

customElements.define("click-spark", ClickSpark);
