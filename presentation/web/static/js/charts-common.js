// ========================================
// SHARED CHART UTILITIES
// ========================================

/**
 * Truncate text to a maximum length with ellipsis
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length (default 20)
 * @returns {string} Truncated text
 */
function truncateText(text, maxLength = 20) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 1) + '…';
}

/**
 * Generate color palette for charts
 * @param {number} count - Number of colors needed
 * @returns {Array<string>} Array of color hex codes
 */
function generateColors(count) {
    const colors = [
        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
        '#FF9F40', '#FF6384', '#C9CBCF', '#4BC0C0', '#FF6384',
        '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'
    ];
    return colors.slice(0, count);
}

/**
 * Get top-level categories with expenses from tree data
 * @param {Object} tree - Category tree data
 * @returns {Array} Sorted array of top-level categories
 */
function getTopLevelCategories(tree) {
    return tree.children
        .filter(child => child.total > 0)
        .sort((a, b) => b.total - a.total);
}

/**
 * Flatten category tree into a list with levels
 * @param {Object} node - Tree node
 * @param {number} level - Current nesting level
 * @param {Array} result - Accumulator array
 * @returns {Array} Flattened category list
 */
function flattenCategories(node, level = 0, result = []) {
    if (level > 0) {
        result.push({
            id: node.id,
            name: node.name,
            total: node.total,
            level: level - 1,
            percentage: 0,
            hasChildren: node.children && node.children.length > 0
        });
    }

    const sortedChildren = [...(node.children || [])].sort((a, b) => b.total - a.total);
    sortedChildren.forEach(child => flattenCategories(child, level + 1, result));

    return result;
}

/**
 * Create a bar chart
 * @param {string} canvasId - ID of canvas element
 * @param {Object} treeData - Category tree data
 * @param {Function} onCategoryClick - Callback for category click
 * @param {string} currencySymbol - Currency symbol to display (default: '$')
 * @returns {Chart} Chart.js instance
 */
function createBarChart(canvasId, treeData, onCategoryClick, currencySymbol = '$') {
    const topCategories = getTopLevelCategories(treeData);
    const total = treeData.total;

    if (topCategories.length === 0 || total === 0) {
        return null;
    }

    return new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: {
            labels: topCategories.map(c => truncateText(c.name)),
            datasets: [{
                label: `Expense Amount (${currencySymbol})`,
                data: topCategories.map(c => c.total),
                backgroundColor: 'rgba(33, 150, 243, 0.6)',
                borderColor: 'rgba(33, 150, 243, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (event, elements) => {
                if (elements.length > 0 && onCategoryClick) {
                    onCategoryClick(topCategories[elements[0].index].id);
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => currencySymbol + value.toLocaleString()
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            // Show full name in tooltip
                            return topCategories[context[0].dataIndex].name;
                        },
                        label: function(context) {
                            const value = context.parsed.y || 0;
                            const percentage = total > 0 ? (value / total * 100).toFixed(1) : 0;
                            return `${currencySymbol}${value.toLocaleString()} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Create a pie chart
 * @param {string} canvasId - ID of canvas element
 * @param {Object} treeData - Category tree data
 * @param {Function} onCategoryClick - Callback for category click
 * @param {string} currencySymbol - Currency symbol to display (default: '$')
 * @returns {Chart} Chart.js instance
 */
function createPieChart(canvasId, treeData, onCategoryClick, currencySymbol = '$') {
    const topCategories = getTopLevelCategories(treeData);
    const total = treeData.total;

    if (topCategories.length === 0 || total === 0) {
        return null;
    }

    return new Chart(document.getElementById(canvasId), {
        type: 'pie',
        data: {
            labels: topCategories.map(c => truncateText(c.name)),
            datasets: [{
                data: topCategories.map(c => c.total),
                backgroundColor: generateColors(topCategories.length),
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (event, elements) => {
                if (elements.length > 0 && onCategoryClick) {
                    onCategoryClick(topCategories[elements[0].index].id);
                }
            },
            plugins: {
                legend: {
                    position: window.innerWidth < 768 ? 'bottom' : 'right',
                    onClick: (event, legendItem, legend) => {
                        if (onCategoryClick) {
                            onCategoryClick(topCategories[legendItem.index].id);
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            // Show full name in tooltip
                            return topCategories[context[0].dataIndex].name;
                        },
                        label: function(context) {
                            const value = context.parsed || 0;
                            const percentage = total > 0 ? (value / total * 100).toFixed(1) : 0;
                            return `${currencySymbol}${value.toLocaleString()} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Create a stacked bar chart with subcategories
 * @param {string} canvasId - ID of canvas element
 * @param {Object} treeData - Category tree data
 * @param {Function} onCategoryClick - Callback for category click
 * @param {string} currencySymbol - Currency symbol to display (default: '$')
 * @returns {Chart} Chart.js instance
 */
function createStackedBarChart(canvasId, treeData, onCategoryClick, currencySymbol = '$') {
    const topCategories = getTopLevelCategories(treeData);
    const total = treeData.total;

    if (topCategories.length === 0 || total === 0) {
        return null;
    }

    // Helper to collect all categories and calculate direct expenses at each level
    function getCategoriesWithDirectExpenses(node, result = [], parentId = null) {
        const hasChildren = node.children && node.children.length > 0;
        const childrenTotal = hasChildren
            ? node.children.reduce((sum, child) => sum + child.total, 0)
            : 0;
        const directExpenses = node.total - childrenTotal;

        // Add entry for direct expenses at this level
        if (directExpenses > 0) {
            result.push({
                id: node.id,
                name: node.name,
                total: directExpenses,
                parent_id: parentId,
                // isDirect is true only for intermediate nodes (non-leaf with direct expenses)
                // Leaf nodes get isDirect = false so they don't get labeled "(other)"
                isDirect: hasChildren,
                hasChildren: hasChildren
            });
        }

        // Recurse into children
        if (hasChildren) {
            node.children.forEach(child => {
                if (child.total > 0) {
                    getCategoriesWithDirectExpenses(child, result, node.id);
                }
            });
        }

        return result;
    }

    // Prepare category labels (top-level only for x-axis)
    const labels = topCategories.map(c => truncateText(c.name));

    // Collect all subcategories across all top-level categories
    const allSubcategoriesMap = new Map(); // Map<subcategoryId, {name, data[], categoryId, parentId}>

    topCategories.forEach((topCat, topIndex) => {
        const categoriesWithDirectExpenses = getCategoriesWithDirectExpenses(topCat);

        categoriesWithDirectExpenses.forEach(cat => {
            // Create unique key: append "_direct" suffix for intermediate nodes with direct expenses
            const categoryKey = cat.isDirect ? `${cat.id}_direct` : cat.id;

            // Initialize entry if it doesn't exist
            if (!allSubcategoriesMap.has(categoryKey)) {
                const displayName = cat.isDirect ? `${cat.name} (other)` : cat.name;
                allSubcategoriesMap.set(categoryKey, {
                    id: categoryKey,
                    name: truncateText(displayName, 18), // Slightly shorter for stacked legends
                    fullName: displayName, // Keep full name for tooltips
                    data: new Array(topCategories.length).fill(0),
                    parentId: cat.parent_id,
                    isDirect: cat.isDirect
                });
            }
            // Set the value for this top-level category's bar
            allSubcategoriesMap.get(categoryKey).data[topIndex] = cat.total;
        });
    });

    // Convert map to array and sort by total expense DESC (highest first)
    const allSubcategories = Array.from(allSubcategoriesMap.values());
    allSubcategories.forEach(subcat => {
        subcat.totalExpense = subcat.data.reduce((sum, val) => sum + val, 0);
    });
    allSubcategories.sort((a, b) => b.totalExpense - a.totalExpense);

    // Reverse the order so highest expense is rendered first (at the bottom of the stack)
    allSubcategories.reverse();

    // Generate colors - use variations of blue
    // Note: After reversing, highest expenses are first (rendered at bottom)
    // Alpha values: higher index = darker color (more prominent)
    const baseColor = { r: 33, g: 150, b: 243 };
    const datasets = allSubcategories.map((subcat, index) => {
        const alpha = 0.5 + (index / allSubcategories.length) * 0.4; // 0.5 to 0.9
        const rgbaColor = `rgba(${baseColor.r}, ${baseColor.g}, ${baseColor.b}, ${alpha})`;

        return {
            label: subcat.name,
            data: subcat.data,
            backgroundColor: rgbaColor,
            borderColor: `rgba(${baseColor.r}, ${baseColor.g}, ${baseColor.b}, 1)`,
            borderWidth: 0.5,
            categoryId: subcat.id,
            parentId: subcat.parentId
        };
    });

    return new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (event, elements) => {
                if (elements.length > 0 && onCategoryClick) {
                    const barIndex = elements[0].index;
                    onCategoryClick(topCategories[barIndex].id);
                }
            },
            scales: {
                x: {
                    stacked: true
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: {
                        callback: value => currencySymbol + value.toLocaleString()
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return context[0].label;
                        },
                        label: function(context) {
                            // Return empty - we'll use afterBody for custom formatting
                            return '';
                        },
                        afterBody: function(context) {
                            const barIndex = context[0].dataIndex;
                            const topCategory = topCategories[barIndex];

                            // Use top-level category total (it already includes all subcategories)
                            const barTotal = topCategory.total;

                            const lines = [];
                            lines.push(`${topCategory.name}: ${currencySymbol}${barTotal.toLocaleString()}`);

                            // Check if top category has children
                            if (!topCategory.children || topCategory.children.length === 0) {
                                // No subcategories, just show the total
                                return lines;
                            }

                            lines.push(''); // Empty line for spacing

                            // Build hierarchy from tree data (not from datasets)
                            // This shows all levels, not just leaf categories
                            const addNodeRecursively = (node, level) => {
                                if (!node.children || node.children.length === 0) {
                                    return;
                                }

                                // Sort children by total DESC
                                const sortedChildren = [...node.children].sort((a, b) => b.total - a.total);

                                sortedChildren.forEach(child => {
                                    if (child.total > 0) {
                                        const indent = '  '.repeat(level);
                                        const percentage = barTotal > 0 ? ((child.total / barTotal) * 100).toFixed(1) : 0;
                                        lines.push(`${indent}∟ ${child.name}: ${currencySymbol}${child.total.toLocaleString()} (${percentage}%)`);

                                        // Recursively add this child's children
                                        addNodeRecursively(child, level + 1);
                                    }
                                });
                            };

                            addNodeRecursively(topCategory, 1);

                            return lines;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Populate category breakdown table
 * @param {string} tableBodyId - ID of table tbody element
 * @param {Object} treeData - Category tree data
 * @param {Function} onCategoryClick - Callback for category click
 * @param {string} currencySymbol - Currency symbol to display (default: '$')
 */
function populateCategoryTable(tableBodyId, treeData, onCategoryClick, currencySymbol = '$') {
    const allCategories = flattenCategories(treeData);
    const total = treeData.total;

    // Calculate percentages
    allCategories.forEach(cat => {
        cat.percentage = total > 0 ? (cat.total / total * 100).toFixed(1) : 0;
    });

    const tableBody = document.getElementById(tableBodyId);
    tableBody.innerHTML = ''; // Clear existing content

    allCategories.forEach(cat => {
        if (cat.total <= 0) return;

        const row = document.createElement('tr');
        const indentClass = `indent-${Math.min(cat.level, 5)}`;

        row.innerHTML = `
            <td class="${indentClass}">${escapeHtml(cat.name)}</td>
            <td style="text-align: right;">${currencySymbol}${cat.total.toLocaleString()}</td>
            <td style="text-align: right;" class="text-muted">${cat.percentage}%</td>
        `;

        if (onCategoryClick) {
            row.style.cursor = 'pointer';
            row.onclick = () => onCategoryClick(cat.id);
        }

        tableBody.appendChild(row);
    });
}
