import torch

from mmcls.models.backbones.levit import get_LeViT_model

if __name__ == '__main__':
    from torchsummary import summary

    model = get_LeViT_model('LeViT_256')
    # params1 = torch.load('./converters_model_path/LeViT-256.pth')
    # params1 = torch.load('./epoch_31.pth')
    # model.load_state_dict(params1)
    # x = torch.ones((2, 3, 224, 224), device='cuda:0')
    # # x.to("cuda:0")
    # model.to('cuda:0')
    # model.eval()
    # x = model(x)
    # print(x.size())

    params = torch.load('./epoch_31.pth')

    # for name, param in model.named_parameters():
    #     if not param.requires_grad:
    #         continue
    #     if param.ndim <= 1 or name.endswith(".bias") or 'attention_biases' in name:
    #         print(name)
    #
    origin = params['state_dict']
    new = model.state_dict()
    keys = []
    keys1 = []
    print(len(origin), len(new))
    # # print(origin.items())
    for key, _ in origin.items():
        keys.append(key)
        print(key)
    print('------------------------------------------')
    for key, _ in new.items():
        keys1.append(key)
        print(key)
    #
    # change_dict = {}
    # for i in range(len(keys)):
    #     # print('\"%s\": \"%s\",' % (keys[i], keys1[i]))
    #     change_dict[keys1[i]] = keys[i]
    #
    # for i in change_dict:
    #     print("%s\t------------->\t%s" % (change_dict[i], i))
    # with torch.no_grad():
    #     for name, param in new.items():
    #         param.copy_(origin[change_dict[name]])
    #
    # torch.save(new, './converters_model_path/LeViT-256-epoch_29-c.pth')
    # print('success save')
