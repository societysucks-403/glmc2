// Global variables for charts
let derivativeChart, integralChart, limitChart;

// Initialize charts when page loads
document.addEventListener('DOMContentLoaded', function() {
    initializeCharts();
    updateDerivative();
    updateIntegral();
    updateLimit();
});

// Initialize all charts
function initializeCharts() {
    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                position: 'top'
            }
        },
        scales: {
            x: {
                type: 'linear',
                position: 'center',
                grid: {
                    color: 'rgba(0, 0, 0, 0.1)'
                }
            },
            y: {
                type: 'linear',
                position: 'center',
                grid: {
                    color: 'rgba(0, 0, 0, 0.1)'
                }
            }
        }
    };

    // Derivative Chart
    const derivativeCtx = document.getElementById('derivative-chart').getContext('2d');
    derivativeChart = new Chart(derivativeCtx, {
        type: 'line',
        data: {
            datasets: []
        },
        options: chartOptions
    });

    // Integral Chart
    const integralCtx = document.getElementById('integral-chart').getContext('2d');
    integralChart = new Chart(integralCtx, {
        type: 'line',
        data: {
            datasets: []
        },
        options: chartOptions
    });

    // Limit Chart
    const limitCtx = document.getElementById('limit-chart').getContext('2d');
    limitChart = new Chart(limitCtx, {
        type: 'line',
        data: {
            datasets: []
        },
        options: chartOptions
    });
}

// Generate function data points
function generateFunctionData(func, xMin, xMax, step = 0.1) {
    const data = [];
    try {
        for (let x = xMin; x <= xMax; x += step) {
            const y = math.evaluate(func, { x: x });
            if (isFinite(y)) {
                data.push({ x: x, y: y });
            }
        }
    } catch (error) {
        console.error('Error evaluating function:', error);
        return [];
    }
    return data;
}

// Calculate derivative numerically
function calculateDerivative(func, x, h = 0.0001) {
    try {
        const f1 = math.evaluate(func, { x: x + h });
        const f2 = math.evaluate(func, { x: x - h });
        return (f1 - f2) / (2 * h);
    } catch (error) {
        console.error('Error calculating derivative:', error);
        return 0;
    }
}

// Calculate integral numerically (trapezoidal rule)
function calculateIntegral(func, xStart, xEnd, steps = 1000) {
    try {
        const h = (xEnd - xStart) / steps;
        let integral = 0;
        
        for (let i = 0; i <= steps; i++) {
            const x = xStart + i * h;
            const y = math.evaluate(func, { x: x });
            if (i === 0 || i === steps) {
                integral += y / 2;
            } else {
                integral += y;
            }
        }
        
        return integral * h;
    } catch (error) {
        console.error('Error calculating integral:', error);
        return 0;
    }
}

// Update derivative visualization
function updateDerivative() {
    const funcInput = document.getElementById('derivative-func').value;
    const point = parseFloat(document.getElementById('derivative-point').value);
    
    try {
        // Generate function data
        const funcData = generateFunctionData(funcInput, -5, 5, 0.1);
        
        // Calculate derivative
        const derivative = calculateDerivative(funcInput, point);
        
        // Generate tangent line data
        const tangentData = [];
        for (let x = -5; x <= 5; x += 0.1) {
            const y = math.evaluate(funcInput, { x: point }) + derivative * (x - point);
            tangentData.push({ x: x, y: y });
        }
        
        // Update chart
        derivativeChart.data.datasets = [
            {
                label: `f(x) = ${funcInput}`,
                data: funcData,
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                fill: false,
                tension: 0.1
            },
            {
                label: `f'(x) at x=${point}`,
                data: tangentData,
                borderColor: '#ff6b6b',
                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                fill: false,
                borderDash: [5, 5]
            }
        ];
        
        derivativeChart.update();
        
        // Update results
        document.getElementById('derivative-result').textContent = `f'(x) = ${derivative.toFixed(4)}`;
        document.getElementById('tangent-result').textContent = 
            `Tangent at x=${point}: y = ${derivative.toFixed(4)}x + ${(-derivative * point + math.evaluate(funcInput, { x: point })).toFixed(4)}`;
        document.getElementById('slope-result').textContent = `Slope at x=${point}: ${derivative.toFixed(4)}`;
        
    } catch (error) {
        showError('derivative-error', 'Invalid function. Please check your input.');
    }
}

// Update integral visualization
function updateIntegral() {
    const funcInput = document.getElementById('integral-func').value;
    const xStart = parseFloat(document.getElementById('integral-start').value);
    const xEnd = parseFloat(document.getElementById('integral-end').value);
    
    try {
        // Generate function data
        const funcData = generateFunctionData(funcInput, xStart - 2, xEnd + 2, 0.1);
        
        // Calculate integral
        const integral = calculateIntegral(funcInput, xStart, xEnd);
        
        // Generate area fill data
        const areaData = [];
        for (let x = xStart; x <= xEnd; x += 0.1) {
            const y = math.evaluate(funcInput, { x: x });
            areaData.push({ x: x, y: y });
        }
        
        // Update chart
        integralChart.data.datasets = [
            {
                label: `f(x) = ${funcInput}`,
                data: funcData,
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                fill: false,
                tension: 0.1
            },
            {
                label: 'Area under curve',
                data: areaData,
                borderColor: '#51cf66',
                backgroundColor: 'rgba(81, 207, 102, 0.3)',
                fill: 'origin',
                tension: 0.1
            }
        ];
        
        integralChart.update();
        
        // Update results
        document.getElementById('integral-result').textContent = 
            `∫${xStart}^${xEnd} ${funcInput} dx = ${integral.toFixed(4)}`;
        document.getElementById('area-result').textContent = 
            `Area under curve: ${integral.toFixed(4)} square units`;
        
    } catch (error) {
        showError('integral-error', 'Invalid function or range. Please check your input.');
    }
}

// Update limit visualization
function updateLimit() {
    const funcInput = document.getElementById('limit-func').value;
    const point = parseFloat(document.getElementById('limit-point').value);
    const direction = document.querySelector('input[name="direction"]:checked').value;
    
    try {
        let xMin, xMax;
        
        switch (direction) {
            case 'left':
                xMin = point - 3;
                xMax = point;
                break;
            case 'right':
                xMin = point;
                xMax = point + 3;
                break;
            default:
                xMin = point - 3;
                xMax = point + 3;
        }
        
        // Generate function data
        const funcData = generateFunctionData(funcInput, xMin, xMax, 0.01);
        
        // Calculate limit
        let limitValue;
        if (direction === 'both') {
            // Check if left and right limits match
            const leftLimit = calculateLimit(funcInput, point, 'left');
            const rightLimit = calculateLimit(funcInput, point, 'right');
            
            if (Math.abs(leftLimit - rightLimit) < 0.001) {
                limitValue = leftLimit;
            } else {
                limitValue = 'DNE';
            }
        } else {
            limitValue = calculateLimit(funcInput, point, direction);
        }
        
        // Update chart
        limitChart.data.datasets = [
            {
                label: `f(x) = ${funcInput}`,
                data: funcData,
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                fill: false,
                tension: 0.1
            }
        ];
        
        // Add vertical line at limit point
        if (direction === 'both') {
            limitChart.data.datasets.push({
                label: 'x = ' + point,
                data: [{ x: point, y: -10 }, { x: point, y: 10 }],
                borderColor: '#ff6b6b',
                backgroundColor: 'transparent',
                borderDash: [5, 5],
                showLine: true,
                pointRadius: 0
            });
        }
        
        limitChart.update();
        
        // Update results
        if (limitValue === 'DNE') {
            document.getElementById('limit-result').textContent = 
                `limₓ→${point} ${funcInput} = Does Not Exist`;
            document.getElementById('approach-result').textContent = 
                'Left and right limits do not match';
        } else {
            document.getElementById('limit-result').textContent = 
                `limₓ→${point} ${funcInput} = ${limitValue.toFixed(4)}`;
            document.getElementById('approach-result').textContent = 
                `Function approaches ${limitValue.toFixed(4)} as x approaches ${point}`;
        }
        
    } catch (error) {
        showError('limit-error', 'Invalid function. Please check your input.');
    }
}

// Calculate limit numerically
function calculateLimit(func, point, direction) {
    const h = 0.0001;
    let x;
    
    if (direction === 'left') {
        x = point - h;
    } else if (direction === 'right') {
        x = point + h;
    } else {
        // Average of left and right
        const left = math.evaluate(func, { x: point - h });
        const right = math.evaluate(func, { x: point + h });
        return (left + right) / 2;
    }
    
    return math.evaluate(func, { x: x });
}

// Load predefined examples
function loadExample(type) {
    switch (type) {
        case 'polynomial':
            document.getElementById('derivative-func').value = 'x^3 - 3*x^2 + 2*x';
            document.getElementById('integral-func').value = 'x^3 - 3*x^2 + 2*x';
            document.getElementById('limit-func').value = '(x^2 - 4)/(x - 2)';
            break;
        case 'trigonometric':
            document.getElementById('derivative-func').value = 'sin(x)';
            document.getElementById('integral-func').value = 'sin(x)';
            document.getElementById('limit-func').value = '(1 - cos(x))/x';
            break;
        case 'exponential':
            document.getElementById('derivative-func').value = 'exp(x)';
            document.getElementById('integral-func').value = 'exp(x)';
            document.getElementById('limit-func').value = '(exp(x) - 1)/x';
            break;
        case 'rational':
            document.getElementById('derivative-func').value = '1/(x^2 + 1)';
            document.getElementById('integral-func').value = '1/(x^2 + 1)';
            document.getElementById('limit-func').value = '(2*x + 3)/(x + 1)';
            break;
    }
    
    // Update all visualizations
    updateDerivative();
    updateIntegral();
    updateLimit();
}

// Show error message
function showError(elementId, message) {
    const errorElement = document.getElementById(elementId);
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
        setTimeout(() => {
            errorElement.style.display = 'none';
        }, 5000);
    }
}

// Add smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey || e.metaKey) {
        switch (e.key) {
            case '1':
                e.preventDefault();
                document.getElementById('derivatives').scrollIntoView();
                break;
            case '2':
                e.preventDefault();
                document.getElementById('integrals').scrollIntoView();
                break;
            case '3':
                e.preventDefault();
                document.getElementById('limits').scrollIntoView();
                break;
        }
    }
});

// Auto-update visualizations when inputs change
document.getElementById('derivative-func').addEventListener('input', debounce(updateDerivative, 500));
document.getElementById('derivative-point').addEventListener('input', debounce(updateDerivative, 500));
document.getElementById('integral-func').addEventListener('input', debounce(updateIntegral, 500));
document.getElementById('integral-start').addEventListener('input', debounce(updateIntegral, 500));
document.getElementById('integral-end').addEventListener('input', debounce(updateIntegral, 500));
document.getElementById('limit-func').addEventListener('input', debounce(updateLimit, 500));
document.getElementById('limit-point').addEventListener('input', debounce(updateLimit, 500));

// Debounce function to prevent excessive updates
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}