// Performance monitoring and optimization utilities

class PerformanceMonitor {
    constructor() {
        this.metrics = {};
        this.startTime = performance.now();
        this.init();
    }

    init() {
        // Monitor page load performance
        this.monitorPageLoad();
        
        // Monitor resource loading
        this.monitorResources();
        
        // Monitor user interactions
        this.monitorInteractions();
        
        // Monitor memory usage
        this.monitorMemory();
        
        // Monitor network requests
        this.monitorNetwork();
    }

    monitorPageLoad() {
        window.addEventListener('load', () => {
            const navigation = performance.getEntriesByType('navigation')[0];
            const paint = performance.getEntriesByType('paint');
            
            this.metrics.pageLoad = {
                totalLoadTime: navigation.loadEventEnd - navigation.loadEventStart,
                domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                firstPaint: paint.find(p => p.name === 'first-paint')?.startTime || 0,
                firstContentfulPaint: paint.find(p => p.name === 'first-contentful-paint')?.startTime || 0,
                largestContentfulPaint: this.getLargestContentfulPaint(),
                timeToInteractive: this.getTimeToInteractive()
            };

            console.log('Page Load Metrics:', this.metrics.pageLoad);
            this.sendMetrics('pageLoad', this.metrics.pageLoad);
        });
    }

    monitorResources() {
        const observer = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
                if (entry.entryType === 'resource') {
                    this.metrics.resources = this.metrics.resources || [];
                    this.metrics.resources.push({
                        name: entry.name,
                        duration: entry.duration,
                        size: entry.transferSize,
                        type: entry.initiatorType
                    });
                }
            });
        });

        observer.observe({ entryTypes: ['resource'] });
    }

    monitorInteractions() {
        let lastInteraction = performance.now();
        
        const events = ['click', 'keypress', 'scroll', 'mousemove'];
        events.forEach(eventType => {
            document.addEventListener(eventType, () => {
                lastInteraction = performance.now();
            }, { passive: true });
        });

        // Monitor idle time
        setInterval(() => {
            const idleTime = performance.now() - lastInteraction;
            if (idleTime > 5000) { // 5 seconds
                this.metrics.idleTime = idleTime;
            }
        }, 1000);
    }

    monitorMemory() {
        if ('memory' in performance) {
            setInterval(() => {
                this.metrics.memory = {
                    usedJSHeapSize: performance.memory.usedJSHeapSize,
                    totalJSHeapSize: performance.memory.totalJSHeapSize,
                    jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
                };
            }, 10000); // Every 10 seconds
        }
    }

    monitorNetwork() {
        if ('connection' in navigator) {
            this.metrics.network = {
                effectiveType: navigator.connection.effectiveType,
                downlink: navigator.connection.downlink,
                rtt: navigator.connection.rtt,
                saveData: navigator.connection.saveData
            };
        }
    }

    getLargestContentfulPaint() {
        return new Promise((resolve) => {
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                resolve(lastEntry.startTime);
            });
            
            observer.observe({ entryTypes: ['largest-contentful-paint'] });
        });
    }

    getTimeToInteractive() {
        // Estimate TTI based on when the page becomes responsive
        return new Promise((resolve) => {
            let tti = 0;
            const checkTTI = () => {
                if (document.readyState === 'complete') {
                    tti = performance.now();
                    resolve(tti);
                } else {
                    requestAnimationFrame(checkTTI);
                }
            };
            checkTTI();
        });
    }

    sendMetrics(type, data) {
        // Send metrics to server for analysis
        fetch('/api/metrics', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: type,
                data: data,
                timestamp: Date.now(),
                userAgent: navigator.userAgent
            })
        }).catch(error => {
            console.log('Failed to send metrics:', error);
        });
    }

    getMetrics() {
        return this.metrics;
    }
}

// Performance optimization utilities
class PerformanceOptimizer {
    constructor() {
        this.init();
    }

    init() {
        this.optimizeImages();
        this.optimizeFonts();
        this.optimizeScripts();
        this.optimizeCSS();
    }

    optimizeImages() {
        // Lazy load images
        const images = document.querySelectorAll('img[data-src]');
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    observer.unobserve(img);
                }
            });
        });

        images.forEach(img => imageObserver.observe(img));
    }

    optimizeFonts() {
        // Preload critical fonts
        const fontLinks = document.querySelectorAll('link[rel="preload"][as="font"]');
        fontLinks.forEach(link => {
            link.addEventListener('load', () => {
                link.rel = 'stylesheet';
            });
        });
    }

    optimizeScripts() {
        // Defer non-critical scripts
        const scripts = document.querySelectorAll('script[data-defer]');
        scripts.forEach(script => {
            script.defer = true;
        });
    }

    optimizeCSS() {
        // Inline critical CSS
        const criticalCSS = document.querySelector('style[data-critical]');
        if (criticalCSS) {
            document.head.appendChild(criticalCSS);
        }
    }
}

// Debounce utility for performance
function debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func(...args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func(...args);
    };
}

// Throttle utility for performance
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Request animation frame utility
function requestAnimationFramePolyfill() {
    return window.requestAnimationFrame ||
           window.webkitRequestAnimationFrame ||
           window.mozRequestAnimationFrame ||
           function(callback) {
               window.setTimeout(callback, 1000 / 60);
           };
}

// Initialize performance monitoring
const performanceMonitor = new PerformanceMonitor();
const performanceOptimizer = new PerformanceOptimizer();

// Export for use in other scripts
window.PerformanceMonitor = PerformanceMonitor;
window.PerformanceOptimizer = PerformanceOptimizer;
window.debounce = debounce;
window.throttle = throttle;
window.requestAnimationFramePolyfill = requestAnimationFramePolyfill;