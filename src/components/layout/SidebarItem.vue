<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({
  title: {
    type: String,
    required: true,
    default: 'New Chat'
  },
  active: {
    type: Boolean,
    default: false
  },
  onDelete: {
    type: Function,
    default: () => {}
  },
  onRename: {
    type: Function,
    default: () => {}
  }
  ,
  collapsed: {
    type: Boolean,
    default: false
  }
})

// const emit = defineEmits(['select', 'delete', 'rename']) // Removed emits

const showMenu = ref(false)
const menuStyle = ref({ top: '0px', left: '0px' })
const menuBtnRef = ref(null)

const toggleMenu = async (e) => {
  e.stopPropagation()
  showMenu.value = !showMenu.value
  
  if (showMenu.value) {
    await nextTick()
    const rect = menuBtnRef.value.getBoundingClientRect()
    // Position menu
    menuStyle.value = {
      top: `${rect.bottom + 5}px`,
      left: `${rect.right - 100}px` 
    }
  }
}

const handleAction = (action) => {
  // Call prop function directly
  if (action === 'rename') {
    props.onRename()
  } else if (action === 'delete') {
    props.onDelete()
  }
  
  // Close menu after action
  showMenu.value = false
}
</script>

<template>
  <div 
    class="sidebar-item" 
    :class="{ 'is-active': active }"
  >
<!-- Note: Keep select as emit since it works fine on the main div -->
    <div class="item-content" @click="$emit('select')">
      <div class="icon">
        <i class="ph ph-chat-circle"></i>
      </div>
      <span v-if="!collapsed" class="title">{{ title }}</span>
    </div>
    
    <!-- Actions Toggle -->
    <div class="actions-wrapper" v-if="!collapsed">
      <button ref="menuBtnRef" class="icon-btn menu-btn" @click="toggleMenu">
        <i class="ph ph-dots-three"></i>
      </button>

      <!-- Teleported Dropdown Menu -->
      <Teleport to="body">
        <!-- Overlay for closing -->
        <div v-if="showMenu" class="menu-overlay" @click="showMenu = false"></div>
        
        <!-- Menu Itself -->
        <div v-if="showMenu" class="dropdown-menu" :style="menuStyle">
          <button type="button" class="dropdown-item" @click.stop="handleAction('rename')">
            <i class="ph ph-pencil-simple"></i>
            Rename
          </button>
          <button type="button" class="dropdown-item delete" @click.stop="handleAction('delete')">
            <i class="ph ph-trash"></i>
            Delete
          </button>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<style scoped>
/* Previous styles remain... */
.sidebar-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  margin: var(--space-1) var(--space-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  text-decoration: none;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: visible; 
  position: relative;
}

.sidebar-item:hover, .sidebar-item.is-active {
  background: var(--bg-surface);
  color: var(--text-primary);
}

.sidebar-item:hover .menu-btn {
  opacity: 1;
}

.item-content {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: 1;
  cursor: pointer;
}

.icon {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
}

.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Menu Button */
.actions-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.menu-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0; 
  transition: opacity var(--transition-fast);
}

.menu-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
}

.sidebar-item.is-active .menu-btn,
.sidebar-item .menu-btn:focus {
  opacity: 1;
}

/* Dropdown Styles - Now scoped but teleport target needs styles accessible or global?
   Scoped styles in Vue do NOT apply to Teleported content unless using :deep or global CSS.
   Let's use a trick: keep styles here but realize Teleport moves it out.
   Actually, the scoped ID is still applied to the VNode, so as long as the CSS is on the component, it *should* work if the structure matches.
   BUT for Teleport to body, scoped styles often fail if the body doesn't share the scope ID (it doesn't).
   
   Better fix: Use <style> without scoped for the specific dropdown classes, or use :global().
*/
</style>

<style>
/* Global styles for teleported menu to ensure it works outside */
.menu-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9998; /* Behind dropdown */
  cursor: default;
}

.dropdown-menu {
  position: fixed; /* Fixed relative to viewport since in body */
  background: #1e293b; /* Hardcode var(--bg-secondary) or similar */
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 0.5rem;
  box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
  padding: 0.25rem;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 9999; /* On top of overlay */
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem;
  text-align: left;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 0.85rem;
  border-radius: 0.25rem;
}

.dropdown-item:hover {
  background: #334155;
  color: #f8fafc;
}

.dropdown-item.delete:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}
</style>
