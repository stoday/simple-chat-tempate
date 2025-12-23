<script setup>
import { onMounted } from 'vue'
import { useAppConfigStore } from './stores/appConfig'

const appConfigStore = useAppConfigStore()

onMounted(() => {
  appConfigStore.loadConfig()
})
</script>

<template>
  <router-view></router-view>
</template>

<style>
/* Global resets or transitions can go here */
</style>
