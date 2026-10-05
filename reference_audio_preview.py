"""Audition the prepared reference audio actually carried by conditioning."""


class SkebaH3ReferenceAudioPreview:
    CATEGORY = "Skeba AI Nodes - Reference"
    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "details")
    FUNCTION = "decode"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "conditioning": ("CONDITIONING",),
            "audio_vae": ("VAE",),
            "audio_number": ("INT", {"default": 1, "min": 1,
                "tooltip": "Audio ordinal in Apply's reference diagnostic. Includes native audio and video soundtracks."}),
            "conditioning_entry": ("INT", {"default": 0, "min": 0}),
        }}

    def decode(self, conditioning, audio_vae, audio_number=1, conditioning_entry=0):
        if not conditioning or not 0 <= conditioning_entry < len(conditioning):
            raise ValueError("No such conditioning entry. Connect SKEBA Apply H3 RefMod's conditioning output.")
        refs = conditioning[conditioning_entry][1].get("minimax_refs", [])
        audios = [(index, block) for index, block in enumerate(refs)
                  if block.get("audio_latent") is not None and int(block.get("ref_audio_t", 0)) > 0]
        if not 1 <= audio_number <= len(audios):
            raise ValueError(f"Audio {audio_number} is unavailable: this conditioning contains {len(audios)} audio reference(s).")
        index, block = audios[audio_number - 1]
        # Decode the post-crop/post-Apply tensor without changing the conditioning.
        waveform = audio_vae.decode(block["audio_latent"].clone()).movedim(-1, 1)
        rate = int(getattr(audio_vae, "audio_sample_rate_output", getattr(audio_vae, "audio_sample_rate", 32000)))
        details = (f"Audio {audio_number}; conditioning entry {conditioning_entry}; block {index}; "
                   f"{block.get('kind')}; {waveform.shape[-1] / rate:.3f}s at {rate} Hz. "
                   "Decoded prepared reference, without loudness normalization. "
                   "Compare this ordinal with Apply's reference diagnostic for ownership.")
        return {"waveform": waveform, "sample_rate": rate}, details
