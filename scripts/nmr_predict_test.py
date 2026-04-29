from app.services.nmr_server_service import nmr_server_service

h_shifts_input = "3.19,3.94,7.04,7.95"
h_split_input = "s,s,d,d"
c_shifts_input = "34.83,55.91,114.90,127.37"
formula = ""
allowed_elements = ""
candidates = ""
reverse_res = nmr_server_service.reverse_predict(
    h_shifts_input,
    h_split_input,
    c_shifts_input,
    formula,
    allowed_elements,
    candidates,
)

# reverse_predict_smiles = []
# for info in reverse_res[:10]:
#     reverse_predict_smiles.append(info["smiles"])
#
# print(reverse_predict_smiles)

reverse_predict_smiles = []
database_res = nmr_server_service.database_search(
    h_shifts_input,
    h_split_input,
    c_shifts_input,
    num_search=500,
    topk=10,
    allowed_elements="",
)
print(database_res)
for info in database_res:
    reverse_predict_smiles.append(info["smiles"])
print(reverse_predict_smiles)