import axios from 'axios'

async function cardBuilderRequest(method: string, params: {}) {
  const response = await axios.post(
    'https://mtgcardbuilder.com/wp-admin/admin-ajax.php',
    { method, ...params },
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  )

  return response.data
}

type Bounds = { x: number; y: number; width: number; height: number }

type BottomInfo = {
  align?: string
  color: string
  font: string
  height: number
  name?: string
  oneLine: boolean
  outlineWidth: number
  size: number
  text: string
  width: number
  x: number
  y: number
}

async function getCardData(id: number) {
  const response = await cardBuilderRequest('getCardData', { id: id })

  return JSON.parse(response.data) as {
    artBounds: Bounds
    artOverlayRotate: number
    artOverlaySource: string
    artOverlayX: number
    artOverlayY: number
    artOverlayZoom: number
    artRotate: string
    artSource: string
    artX: number
    artY: number
    artZoom: number
    bottomInfo: {
      bottomLeft: BottomInfo
      bottomRight: BottomInfo
      midLeft: BottomInfo
      topLeft: BottomInfo
      wizards: BottomInfo
    }
    customManaSymbols: unknown[]
    frames: {
      bounds?: Bounds
      complementary?: number[]
      image: {}
      masks: unknown[]
      name: string
      src: string
    }[]
    height: number
    illus: string
    infoArtist: string
    infoLanguage: string
    infoNumber: string
    infoRarity: string
    infoSet: string
    infoYear: string
    manaSymbols: unknown[]
    marginX: number
    marginY: number
    margins: boolean
    onload: null
    setSymbolBounds: Bounds & { vertical: string; horizontal: string }
    setSymbolSource: string
    setSymbolX: number
    setSymbolY: number
    setSymbolZoom: number
    signature1: string
    signature2: string
    text: {
      [id: string]: {
        align?: string
        color?: string
        font?: string
        height: number
        manaCost?: boolean
        manaSpacing?: number
        name: string
        oneLine?: boolean
        shadowX?: number
        shadowY?: number
        size: number
        text: string
        width: number
        x?: number
        y: number
      }
    }
    version: string
    watermarkBounds: Bounds
    watermarkLeft: string
    watermarkOpacity: number
    watermarkRight: string
    watermarkSource: string
    watermarkX: number
    watermarkY: number
    watermarkZoom: number
    width: number
  }
}

async function getCards(options: {
  category?: string
  cpage?: number
  isDashboard?: string
  lang?: string
  nsfw?: number
  order?: string
  other?: number
  showIsDashboard?: string
}) {
  return (await cardBuilderRequest('get_gallery_cards', options)) as {
    current: number
    data: {
      artist_name: string
      card_edition: string
      card_id: string | null
      category: string
      dislikes: string | null
      email: string
      face: string
      id: string
      image_url: string
      likes: string | null
      nsfw: string
      pp_id: null
      prints_regular: string
      search_card_name: string
      status: string
      tags: string
      user_id: string
      user_name: string
      visual_type: string
    }[]
    is: string
    liked: unknown[]
    total: number
  }
}
