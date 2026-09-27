#!/usr/bin/env node
import { readFileSync, readdirSync, existsSync, renameSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const release = join(root, 'src-tauri', 'target', 'release')
const macDir = join(release, 'bundle', 'macos')
const dmgDir = join(release, 'bundle', 'dmg')

const CPU_X86_64 = 0x01000007
const CPU_ARM64 = 0x0100000c
const FAT_MAGIC = 0xcafebabe    // universal, big-endian layout
const FAT_CIGAM = 0xbebafeca    // universal, little-endian layout
const MH_MAGIC_64 = 0xfeedfacf  // thin 64-bit, little-endian layout

function detectCpuTypes(buf) {
  const magicBE = buf.readUInt32BE(0)
  const magicLE = buf.readUInt32LE(0)

  if (magicBE === FAT_MAGIC) {
    const nfat = buf.readUInt32BE(4)
    const cpus = []
    for (let i = 0; i < nfat; i++) cpus.push(buf.readUInt32BE(8 + i * 20))
    return cpus
  }
  if (magicLE === FAT_CIGAM) {
    const nfat = buf.readUInt32LE(4)
    const cpus = []
    for (let i = 0; i < nfat; i++) cpus.push(buf.readUInt32LE(8 + i * 20))
    return cpus
  }
  if (magicLE === MH_MAGIC_64) {
    return [buf.readUInt32LE(4)]
  }
  return []
}

function archName(cpus) {
  if (cpus.includes(CPU_ARM64) && cpus.includes(CPU_X86_64)) return 'universal'
  if (cpus.includes(CPU_ARM64)) return 'aarch64'
  if (cpus.includes(CPU_X86_64)) return 'x64'
  return null
}

function findAppBundle() {
  if (!existsSync(macDir)) return null
  return readdirSync(macDir).find((d) => d.endsWith('.app'))
}

function findMainBinary(appBundle) {
  const macOsDir = join(macDir, appBundle, 'Contents', 'MacOS')
  if (!existsSync(macOsDir)) return null

  const fallback = join(macOsDir, appBundle.replace(/\.app$/, ''))
  if (existsSync(fallback)) return fallback

  return readdirSync(macOsDir)
    .map((name) => join(macOsDir, name))
    .find((p) => {
      try {
        return statSync(p).isFile() && p !== fallback
      } catch {
        return false
      }
    })
}

const appBundle = findAppBundle()
if (!appBundle) {
  console.log('[fix-dmg-arch] no .app bundle found, nothing to do')
  process.exit(0)
}

const mainBinary = findMainBinary(appBundle)
if (!mainBinary || !existsSync(mainBinary)) {
  console.error(`[fix-dmg-arch] main binary not found: ${mainBinary}`)
  process.exit(1)
}

let buf
try {
  buf = readFileSync(mainBinary)
} catch {
  console.error(`[fix-dmg-arch] cannot read: ${mainBinary}`)
  process.exit(1)
}

const arch = archName(detectCpuTypes(buf))
if (!arch) {
  console.error(`[fix-dmg-arch] unsupported Mach-O layout in ${mainBinary}`)
  process.exit(1)
}

if (!existsSync(dmgDir) || readdirSync(dmgDir).filter((f) => f.endsWith('.dmg')).length === 0) {
  console.log(`[fix-dmg-arch] no dmg at ${dmgDir}, nothing to do`)
  process.exit(0)
}

const ARCH_MARK = /_(?:x64|x86_64|aarch64|arm64|universal)(?=\.dmg$)/
for (const file of readdirSync(dmgDir).filter((f) => f.endsWith('.dmg'))) {
  if (!ARCH_MARK.test(file)) continue
  const fixed = file.replace(ARCH_MARK, `_${arch}`)
  if (fixed === file) {
    console.log(`[fix-dmg-arch] ${file} already correct (${arch})`)
    continue
  }
  renameSync(join(dmgDir, file), join(dmgDir, fixed))
  console.log(`[fix-dmg-arch] renamed ${file} -> ${fixed}`)
}